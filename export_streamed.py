#!/usr/bin/env python3
"""
Phase 2: Stream from aggregated SQLite table to PostgreSQL with row-level checkpointing.

Features:
- Streams rows using cursor iteration (no fetchall)
- Row-level checkpointing after each batch
- Atomic checkpoint writes
- Exponential backoff on connection failures
- UPSERT to handle duplicates
"""

import sqlite3
import psycopg2
import psycopg2.extras
import os
import sys
import time
import tempfile

# Configuration
SQLITE_PATH = 'bdc_internet_new.db'
CHECKPOINT_FILE = 'export_streamed_checkpoint.txt'
BATCH_SIZE = 5000
MAX_RETRIES = 5
INITIAL_BACKOFF = 2  # seconds

# Get PostgreSQL URL from environment or use default
PG_URL = os.environ.get('DATABASE_URL', 
    'postgresql://postgres:uLsIMDrAWOhRMynIASQVrRcHpnCfLRki@gondola.proxy.rlwy.net:21850/railway')


def load_checkpoint():
    """Load last successfully exported block_geoid."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            return f.read().strip()
    return None


def save_checkpoint(block_geoid):
    """Atomically save checkpoint using tmp file + rename."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(CHECKPOINT_FILE) or '.')
    try:
        with os.fdopen(tmp_fd, 'w') as f:
            f.write(block_geoid)
        os.replace(tmp_path, CHECKPOINT_FILE)
    except:
        os.unlink(tmp_path)
        raise


def get_pg_connection():
    """Get PostgreSQL connection with retry logic and exponential backoff."""
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            conn = psycopg2.connect(PG_URL, connect_timeout=30)
            conn.autocommit = False
            return conn
        except Exception as e:
            print(f"  Connection attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"  Retrying in {backoff} seconds...")
                time.sleep(backoff)
                backoff *= 2
    raise Exception(f"Failed to connect to PostgreSQL after {MAX_RETRIES} retries")


def ensure_table_exists(pg_conn):
    """Create target table if it doesn't exist."""
    with pg_conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS internet_providers (
                block_geoid TEXT PRIMARY KEY,
                providers JSONB NOT NULL
            )
        ''')
        pg_conn.commit()


def export_data():
    """Main export function with streaming and checkpointing."""
    
    # Load checkpoint
    last_block = load_checkpoint()
    if last_block:
        print(f"Resuming from checkpoint: {last_block}")
    else:
        print("Starting fresh export (no checkpoint found)")
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_cursor = sqlite_conn.cursor()
    
    # Check if aggregated table exists
    sqlite_cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='block_providers_agg'"
    )
    if not sqlite_cursor.fetchone():
        print("ERROR: block_providers_agg table not found!")
        print("Run: sqlite3 bdc_internet_new.db < create_aggregated_table.sql")
        sys.exit(1)
    
    # Get total count for progress
    if last_block:
        sqlite_cursor.execute(
            "SELECT COUNT(*) FROM block_providers_agg WHERE block_geoid > ?",
            (last_block,)
        )
    else:
        sqlite_cursor.execute("SELECT COUNT(*) FROM block_providers_agg")
    remaining = sqlite_cursor.fetchone()[0]
    print(f"Rows to export: {remaining:,}")
    
    if remaining == 0:
        print("Export complete! No rows remaining.")
        return True
    
    # Connect to PostgreSQL
    pg_conn = get_pg_connection()
    ensure_table_exists(pg_conn)
    
    # Stream from SQLite with checkpoint resume
    if last_block:
        sqlite_cursor.execute(
            "SELECT block_geoid, providers_json FROM block_providers_agg WHERE block_geoid > ? ORDER BY block_geoid",
            (last_block,)
        )
    else:
        sqlite_cursor.execute(
            "SELECT block_geoid, providers_json FROM block_providers_agg ORDER BY block_geoid"
        )
    
    batch = []
    total_exported = 0
    last_exported_block = last_block
    
    # Stream rows one at a time (no fetchall!)
    for row in sqlite_cursor:
        block_geoid, providers_json = row
        batch.append((block_geoid, providers_json))
        
        if len(batch) >= BATCH_SIZE:
            # Insert batch with retry logic
            success = insert_batch_with_retry(pg_conn, batch)
            if not success:
                print(f"FATAL: Could not insert batch after retries. Last checkpoint: {last_exported_block}")
                return False
            
            total_exported += len(batch)
            last_exported_block = batch[-1][0]
            
            # Save checkpoint
            save_checkpoint(last_exported_block)
            
            # Progress log
            print(f"Exported {total_exported:,} rows | Last block: {last_exported_block}")
            
            batch = []
    
    # Final batch
    if batch:
        success = insert_batch_with_retry(pg_conn, batch)
        if not success:
            print(f"FATAL: Could not insert final batch. Last checkpoint: {last_exported_block}")
            return False
        
        total_exported += len(batch)
        last_exported_block = batch[-1][0]
        save_checkpoint(last_exported_block)
        print(f"Exported {total_exported:,} rows | Last block: {last_exported_block}")
    
    # Cleanup
    sqlite_conn.close()
    pg_conn.close()
    
    print(f"\n✓ Export complete! Total rows exported this run: {total_exported:,}")
    return True


def insert_batch_with_retry(pg_conn, batch):
    """Insert batch with retry logic. Returns True on success."""
    backoff = INITIAL_BACKOFF
    
    for attempt in range(MAX_RETRIES):
        try:
            with pg_conn.cursor() as cur:
                # UPSERT: insert or update on conflict
                psycopg2.extras.execute_values(
                    cur,
                    '''
                    INSERT INTO internet_providers (block_geoid, providers)
                    VALUES %s
                    ON CONFLICT (block_geoid) DO UPDATE SET providers = EXCLUDED.providers
                    ''',
                    batch,
                    template='(%s, %s::jsonb)'
                )
            pg_conn.commit()
            return True
            
        except psycopg2.OperationalError as e:
            print(f"  Batch insert attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            pg_conn.rollback()
            
            if attempt < MAX_RETRIES - 1:
                print(f"  Reconnecting in {backoff} seconds...")
                time.sleep(backoff)
                backoff *= 2
                
                # Try to reconnect
                try:
                    pg_conn.close()
                except:
                    pass
                pg_conn = get_pg_connection()
        
        except Exception as e:
            print(f"  Unexpected error: {e}")
            pg_conn.rollback()
            return False
    
    return False


if __name__ == '__main__':
    start_time = time.time()
    success = export_data()
    elapsed = time.time() - start_time
    
    print(f"\nElapsed time: {elapsed/60:.1f} minutes")
    sys.exit(0 if success else 1)
