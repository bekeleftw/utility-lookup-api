#!/usr/bin/env python3
"""
Export FCC BDC data from SQLite to PostgreSQL (aggregated by census block).
Uses multiprocessing for speed. Only exports Fiber (50) and Cable (40).
"""

import sqlite3
import psycopg2
import json
import multiprocessing as mp
from psycopg2.extras import execute_values
from concurrent.futures import ProcessPoolExecutor, as_completed
import time

# PostgreSQL connection
PG_URL = "postgresql://postgres:uLsIMDrAWOhRMynIASQVrRcHpnCfLRki@gondola.proxy.rlwy.net:21850/railway"

# SQLite source
SQLITE_DB = "bdc_internet_new.db"

# Only include Fiber and Cable (skip wireless/satellite)
TECH_FILTER = ('50', '40')  # 50=Fiber, 40=Cable

BATCH_SIZE = 20000  # Larger batches
NUM_WORKERS = 12    # More workers


def process_batch(block_batch):
    """Process a batch of block_geoids and return aggregated data."""
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    cursor = sqlite_conn.cursor()
    
    results = []
    for block_geoid in block_batch:
        # Only get Fiber and Cable providers
        cursor.execute(
            "SELECT provider_name, technology, max_down, max_up, low_latency FROM providers WHERE block_geoid = ? AND technology IN ('50', '40')",
            (block_geoid,)
        )
        providers = []
        for row in cursor:
            providers.append({
                'name': row[0],
                'tech': row[1],
                'down': row[2] or 0,
                'up': row[3] or 0,
                'low_lat': row[4] or 0
            })
        # Only add if there are providers (skip empty blocks)
        if providers:
            results.append((block_geoid, json.dumps(providers)))
    
    sqlite_conn.close()
    return results


def insert_batch(batch):
    """Insert a batch into PostgreSQL."""
    pg_conn = psycopg2.connect(PG_URL)
    cursor = pg_conn.cursor()
    execute_values(
        cursor,
        "INSERT INTO internet_providers (block_geoid, providers) VALUES %s ON CONFLICT DO NOTHING",
        batch
    )
    pg_conn.commit()
    pg_conn.close()
    return len(batch)


def create_pg_table():
    """Create the aggregated providers table in PostgreSQL."""
    pg_conn = psycopg2.connect(PG_URL)
    cursor = pg_conn.cursor()
    cursor.execute("""
        DROP TABLE IF EXISTS internet_providers;
        CREATE TABLE internet_providers (
            block_geoid VARCHAR(15) PRIMARY KEY,
            providers JSONB NOT NULL
        );
    """)
    pg_conn.commit()
    pg_conn.close()
    print("Created internet_providers table")


def aggregate_and_export():
    """Aggregate SQLite data by block_geoid and export to PostgreSQL with concurrency."""
    
    # Create table
    create_pg_table()
    
    print("Reading unique block_geoids (using index)...")
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    cursor = sqlite_conn.cursor()
    # Use the indexed query - filter happens during processing
    cursor.execute("SELECT DISTINCT block_geoid FROM providers")
    all_blocks = [row[0] for row in cursor.fetchall()]
    sqlite_conn.close()
    
    total_blocks = len(all_blocks)
    print(f"Total blocks to process: {total_blocks:,} (filtering to Fiber/Cable during export)")
    print(f"Using {NUM_WORKERS} workers...")
    
    # Split into batches for processing
    batches = [all_blocks[i:i+BATCH_SIZE] for i in range(0, len(all_blocks), BATCH_SIZE)]
    print(f"Split into {len(batches)} batches of ~{BATCH_SIZE} blocks each")
    
    count = 0
    start_time = time.time()
    
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Submit all processing jobs
        future_to_batch = {executor.submit(process_batch, batch): i for i, batch in enumerate(batches)}
        
        for future in as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                results = future.result()
                # Insert into PostgreSQL
                insert_batch(results)
                count += len(results)
                
                elapsed = time.time() - start_time
                rate = count / elapsed if elapsed > 0 else 0
                eta = (total_blocks - count) / rate if rate > 0 else 0
                print(f"  Inserted {count:,} / {total_blocks:,} ({100*count/total_blocks:.1f}%) - {rate:.0f} blocks/sec - ETA: {eta/60:.1f} min")
            except Exception as e:
                print(f"  Batch {batch_idx} failed: {e}")
    
    print(f"Done! Inserted {count:,} blocks in {(time.time()-start_time)/60:.1f} minutes")
    
    # Create index
    print("Creating index...")
    pg_conn = psycopg2.connect(PG_URL)
    cursor = pg_conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internet_block ON internet_providers(block_geoid)")
    pg_conn.commit()
    pg_conn.close()
    print("Index created")


if __name__ == "__main__":
    aggregate_and_export()
