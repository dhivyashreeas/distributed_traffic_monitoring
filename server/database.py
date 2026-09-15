"""
DISTRIBUTED COMPUTING CONCEPT DEMONSTRATION: CENTRAL DATABASE WITH WAL CONCURRENCY

Role in Distributed Architecture:
- Centralized Data Store backing the Central Monitoring Aggregator.
- Configured with SQLite Write-Ahead Logging (WAL) mode to permit high-concurrency 
  parallel writes from multiple incoming node request worker threads while simultaneously 
  serving read operations to dashboard polling clients without locking deadlocks.
"""

import os
import sqlite3
from datetime import datetime, timezone
import logging

DB_PATH = os.environ.get("DATABASE_PATH", "traffic_monitoring.db")

logger = logging.getLogger("CentralDB")

def get_db_connection():
    """
    Returns a thread-safe connection to the SQLite database.
    Configures timeout and Row factory for dictionary-like column access.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high concurrency across threads/processes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

def init_db():
    """
    Initializes database schema tables if they do not exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Junctions table storing latest reported state for each node
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS junctions (
        junction_id TEXT PRIMARY KEY,
        junction_name TEXT NOT NULL,
        vehicle_count INTEGER NOT NULL,
        avg_speed_kmh REAL NOT NULL,
        weather_condition TEXT NOT NULL,
        congestion_level TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        report_count INTEGER DEFAULT 1
    )
    """)

    # Append-only time-series table logging all historical node telemetry
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS traffic_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        junction_id TEXT NOT NULL,
        vehicle_count INTEGER NOT NULL,
        avg_speed_kmh REAL NOT NULL,
        weather_condition TEXT NOT NULL,
        congestion_level TEXT NOT NULL,
        sequence_num INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (junction_id) REFERENCES junctions (junction_id)
    )
    """)

    # Congestion events & alerts log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS congestion_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        junction_id TEXT NOT NULL,
        junction_name TEXT NOT NULL,
        severity TEXT NOT NULL,
        vehicle_count INTEGER NOT NULL,
        avg_speed_kmh REAL NOT NULL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()
    logger.info("✅ SQLite Database initialized with WAL concurrency enabled.")

def record_node_telemetry(payload: dict, congestion_level: str) -> bool:
    """
    Atomically updates the latest state of the reporting node and appends to history log.
    If congestion is High, logs a central alert event.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
    junction_id = payload["junction_id"]
    name = payload.get("junction_name", f"Junction-{junction_id}")
    count = payload["vehicle_count"]
    speed = payload["avg_speed_kmh"]
    weather = payload.get("weather_condition", "Clear")
    seq = payload.get("sequence_num", 0)

    try:
        # Upsert into junctions table
        cursor.execute("""
        INSERT INTO junctions (junction_id, junction_name, vehicle_count, avg_speed_kmh, weather_condition, congestion_level, last_seen, report_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(junction_id) DO UPDATE SET
            junction_name = excluded.junction_name,
            vehicle_count = excluded.vehicle_count,
            avg_speed_kmh = excluded.avg_speed_kmh,
            weather_condition = excluded.weather_condition,
            congestion_level = excluded.congestion_level,
            last_seen = excluded.last_seen,
            report_count = report_count + 1
        """, (junction_id, name, count, speed, weather, congestion_level, now_iso))

        # Append to historical reports log
        cursor.execute("""
        INSERT INTO traffic_reports (junction_id, vehicle_count, avg_speed_kmh, weather_condition, congestion_level, sequence_num, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (junction_id, count, speed, weather, congestion_level, seq, now_iso))

        # Generate alert if High congestion detected
        if congestion_level == "High":
            msg = f"Heavy congestion detected at {name}: {count} vehicles, avg speed {speed} km/h"
            cursor.execute("""
            INSERT INTO congestion_alerts (junction_id, junction_name, severity, vehicle_count, avg_speed_kmh, message, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (junction_id, name, "HIGH", count, speed, msg, now_iso))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to record telemetry for {junction_id}: {e}")
        return False
    finally:
        conn.close()

def get_all_junctions():
    """
    Returns latest state of all registered nodes.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM junctions ORDER BY junction_id ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_junction_history(junction_id: str, limit: int = 30):
    """
    Returns recent time-series telemetry for a specific node.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM traffic_reports
    WHERE junction_id = ?
    ORDER BY id DESC LIMIT ?
    """, (junction_id, limit))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return list(reversed(rows))

def get_recent_alerts(limit: int = 15):
    """
    Returns recent central congestion alerts.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM congestion_alerts ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
