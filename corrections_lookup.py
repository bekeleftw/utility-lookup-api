#!/usr/bin/env python3
"""
SQLite-based corrections system for utility provider feedback.
Stores user corrections, tracks confirmations, and applies verified corrections to lookups.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, Dict, List

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'corrections.db')

def get_connection():
    """Get a database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the corrections database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Corrections table - stores user-submitted corrections
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utility_type TEXT NOT NULL,
            correct_provider TEXT NOT NULL,
            state TEXT NOT NULL,
            zip_code TEXT,
            city TEXT,
            street TEXT,
            incorrect_provider TEXT,
            source TEXT DEFAULT 'user_feedback',
            full_address TEXT,
            confirmation_count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            verified_at TEXT,
            applied_at TEXT
        )
    ''')
    
    # Confirmations table - tracks who confirmed what
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            correction_id INTEGER,
            address TEXT,
            source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (correction_id) REFERENCES corrections(id)
        )
    ''')
    
    # Verified utilities table - human-verified correct results
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_utilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utility_type TEXT NOT NULL,
            provider_name TEXT NOT NULL,
            state TEXT NOT NULL,
            zip_code TEXT,
            city TEXT,
            address TEXT,
            phone TEXT,
            website TEXT,
            verification_count INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_corrections_zip ON corrections(zip_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_corrections_state ON corrections(state)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_corrections_status ON corrections(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_verified_zip ON verified_utilities(zip_code)')
    
    conn.commit()
    conn.close()

def add_correction(
    utility_type: str,
    correct_provider: str,
    state: str,
    zip_code: Optional[str] = None,
    city: Optional[str] = None,
    street: Optional[str] = None,
    incorrect_provider: Optional[str] = None,
    source: str = 'user_feedback',
    full_address: Optional[str] = None
) -> Dict:
    """
    Add a correction or increment confirmation count if similar exists.
    Returns status and correction ID.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check for existing similar correction
    cursor.execute('''
        SELECT id, confirmation_count, status FROM corrections
        WHERE utility_type = ? AND state = ? AND zip_code = ?
        AND LOWER(correct_provider) = LOWER(?)
        AND status != 'rejected'
    ''', (utility_type, state, zip_code, correct_provider))
    
    existing = cursor.fetchone()
    
    if existing:
        # Increment confirmation count
        new_count = existing['confirmation_count'] + 1
        new_status = 'verified' if new_count >= 3 else 'pending'
        verified_at = datetime.now().isoformat() if new_count >= 3 else None
        
        cursor.execute('''
            UPDATE corrections 
            SET confirmation_count = ?, status = ?, updated_at = ?, verified_at = ?
            WHERE id = ?
        ''', (new_count, new_status, datetime.now().isoformat(), verified_at, existing['id']))
        
        # Log the confirmation
        cursor.execute('''
            INSERT INTO confirmations (correction_id, address, source)
            VALUES (?, ?, ?)
        ''', (existing['id'], full_address, source))
        
        conn.commit()
        conn.close()
        
        return {
            'status': 'updated',
            'id': existing['id'],
            'confirmation_count': new_count,
            'verified': new_count >= 3
        }
    else:
        # Insert new correction
        cursor.execute('''
            INSERT INTO corrections 
            (utility_type, correct_provider, state, zip_code, city, street, 
             incorrect_provider, source, full_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (utility_type, correct_provider, state, zip_code, city, street,
              incorrect_provider, source, full_address))
        
        correction_id = cursor.lastrowid
        
        # Log initial confirmation
        cursor.execute('''
            INSERT INTO confirmations (correction_id, address, source)
            VALUES (?, ?, ?)
        ''', (correction_id, full_address, source))
        
        conn.commit()
        conn.close()
        
        return {
            'status': 'created',
            'id': correction_id,
            'confirmation_count': 1,
            'verified': False
        }

def add_verification(
    utility_type: str,
    provider_name: str,
    state: str,
    zip_code: Optional[str] = None,
    city: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    website: Optional[str] = None
) -> Dict:
    """
    Record that a user verified a utility result as correct.
    Increments verification count if already exists.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check for existing
    cursor.execute('''
        SELECT id, verification_count FROM verified_utilities
        WHERE utility_type = ? AND state = ? AND zip_code = ?
        AND LOWER(provider_name) = LOWER(?)
    ''', (utility_type, state, zip_code, provider_name))
    
    existing = cursor.fetchone()
    
    if existing:
        new_count = existing['verification_count'] + 1
        cursor.execute('''
            UPDATE verified_utilities 
            SET verification_count = ?, updated_at = ?
            WHERE id = ?
        ''', (new_count, datetime.now().isoformat(), existing['id']))
        
        conn.commit()
        conn.close()
        
        return {'status': 'updated', 'id': existing['id'], 'verification_count': new_count}
    else:
        cursor.execute('''
            INSERT INTO verified_utilities 
            (utility_type, provider_name, state, zip_code, city, address, phone, website)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (utility_type, provider_name, state, zip_code, city, address, phone, website))
        
        conn.commit()
        conn.close()
        
        return {'status': 'created', 'id': cursor.lastrowid, 'verification_count': 1}

def get_correction_for_lookup(
    utility_type: str,
    state: str,
    zip_code: str
) -> Optional[Dict]:
    """
    Get a verified correction for a specific lookup.
    Only returns corrections with status='verified'.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT correct_provider, confirmation_count, verified_at
        FROM corrections
        WHERE utility_type = ? AND state = ? AND zip_code = ?
        AND status = 'verified'
        ORDER BY confirmation_count DESC, verified_at DESC
        LIMIT 1
    ''', (utility_type, state, zip_code))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'provider': row['correct_provider'],
            'confirmation_count': row['confirmation_count'],
            'verified_at': row['verified_at']
        }
    return None

def get_pending_corrections(limit: int = 100) -> List[Dict]:
    """Get pending corrections for admin review."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM corrections
        WHERE status = 'pending'
        ORDER BY confirmation_count DESC, created_at DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_verified_corrections(limit: int = 100) -> List[Dict]:
    """Get verified corrections."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM corrections
        WHERE status = 'verified'
        ORDER BY verified_at DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_stats() -> Dict:
    """Get correction statistics."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM corrections")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM corrections WHERE status = 'pending'")
    pending = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM corrections WHERE status = 'verified'")
    verified = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM verified_utilities")
    verified_utils = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM confirmations")
    confirmations = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_corrections': total,
        'pending': pending,
        'verified': verified,
        'verified_utilities': verified_utils,
        'total_confirmations': confirmations
    }

def approve_correction(correction_id: int) -> bool:
    """Manually approve a correction (admin action)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE corrections
        SET status = 'verified', verified_at = ?, updated_at = ?
        WHERE id = ?
    ''', (datetime.now().isoformat(), datetime.now().isoformat(), correction_id))
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return success

def reject_correction(correction_id: int) -> bool:
    """Reject a correction (admin action)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE corrections
        SET status = 'rejected', updated_at = ?
        WHERE id = ?
    ''', (datetime.now().isoformat(), correction_id))
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return success


if __name__ == "__main__":
    # Initialize DB and show stats
    init_db()
    print("Database initialized at:", DB_PATH)
    print("Stats:", get_stats())
