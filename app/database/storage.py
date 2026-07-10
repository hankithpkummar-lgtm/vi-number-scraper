"""
SQLite database storage for found numbers.
"""

import asyncio
import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


class StorageManager:
    """Thread-safe SQLite storage for phone numbers."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize StorageManager.

        Args:
            db_path: Path to SQLite database file
        """
        self._db_path = db_path or settings.DATABASE_PATH
        self._backup_dir = settings.BACKUP_DIR
        self._lock = asyncio.Lock()
        self._upload_queue: List[dict] = []

        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self._backup_dir).mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS numbers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    number TEXT UNIQUE NOT NULL,
                    root INTEGER,
                    compound INTEGER,
                    type TEXT,
                    source TEXT DEFAULT 'scraper',
                    found_at REAL,
                    uploaded INTEGER DEFAULT 0,
                    priority INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_error TEXT DEFAULT '',
                    last_sync_attempt REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Add fail_count column if upgrading from older schema
            try:
                conn.execute("ALTER TABLE numbers ADD COLUMN fail_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute("ALTER TABLE numbers ADD COLUMN last_error TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE numbers ADD COLUMN last_sync_attempt REAL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_numbers_uploaded 
                ON numbers(uploaded)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_numbers_priority 
                ON numbers(priority DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_numbers_number 
                ON numbers(number)
            """)
            conn.commit()
        logger.info(f"Database initialized at {self._db_path}")

    def save_number(self, number_data: dict) -> bool:
        """
        Save a number to the database.

        Args:
            number_data: Dictionary containing number information

        Returns:
            True if saved successfully, False if duplicate
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO numbers 
                    (number, root, compound, type, source, found_at, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        number_data["number"],
                        number_data.get("root", 0),
                        number_data.get("compound", 0),
                        number_data.get("type", "unknown"),
                        number_data.get("source", "scraper"),
                        number_data.get("found_at", time.time()),
                        number_data.get("priority", 0),
                    ),
                )
                conn.commit()
                if cursor.rowcount > 0:
                    logger.debug(f"Number saved: {number_data['number']}")
                    return True
                else:
                    logger.debug(f"Duplicate number skipped: {number_data['number']}")
                    return False
        except sqlite3.Error as e:
            logger.error(f"Database error saving number: {e}")
            return False

    def save_numbers_batch(self, numbers: List[dict]) -> int:
        """
        Save multiple numbers in a batch.

        Args:
            numbers: List of number dictionaries

        Returns:
            Count of successfully saved numbers
        """
        saved_count = 0
        try:
            with sqlite3.connect(self._db_path) as conn:
                for number_data in numbers:
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO numbers 
                        (number, root, compound, type, source, found_at, priority)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            number_data["number"],
                            number_data.get("root", 0),
                            number_data.get("compound", 0),
                            number_data.get("type", "unknown"),
                            number_data.get("source", "scraper"),
                            number_data.get("found_at", time.time()),
                            number_data.get("priority", 0),
                        ),
                    )
                    if cursor.rowcount > 0:
                        saved_count += 1
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Batch save error: {e}")
        return saved_count

    def get_numbers(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "priority DESC, found_at DESC",
    ) -> List[dict]:
        """
        Get numbers from the database.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            order_by: Order by clause

        Returns:
            List of number dictionaries
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    f"""
                    SELECT * FROM numbers 
                    ORDER BY {order_by}
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching numbers: {e}")
            return []

    def get_pending_uploads(self, limit: int = 50) -> List[dict]:
        """
        Get numbers that haven't been uploaded yet.
        Orders by fail_count ASC (retry failed ones first), then priority.

        Args:
            limit: Maximum number of results

        Returns:
            List of pending number dictionaries
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM numbers 
                    WHERE uploaded = 0
                    ORDER BY fail_count ASC, priority DESC, found_at ASC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching pending uploads: {e}")
            return []

    def get_permanently_failed(self, limit: int = 10) -> List[dict]:
        """
        Get numbers that have permanently failed (fail_count >= 5).

        Args:
            limit: Maximum number of results

        Returns:
            List of permanently failed number dictionaries
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM numbers 
                    WHERE uploaded = 0 AND fail_count >= 5
                    ORDER BY fail_count ASC, last_sync_attempt ASC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching permanently failed: {e}")
            return []

    def get_failed_uploads(self, limit: int = 50) -> List[dict]:
        """
        Get numbers that failed to upload (have fail_count > 0).
        Orders by fail_count ASC (least failed first).

        Args:
            limit: Maximum number of results

        Returns:
            List of failed number dictionaries
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM numbers 
                    WHERE uploaded = 0 AND fail_count > 0
                    ORDER BY fail_count ASC, last_sync_attempt ASC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching failed uploads: {e}")
            return []

    def mark_upload_failed(self, number_id: int, error: str = "") -> None:
        """
        Increment fail count and record error for a number.

        Args:
            number_id: ID of the number
            error: Error message from the failed upload
        """
        import time
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    UPDATE numbers 
                    SET fail_count = fail_count + 1,
                        last_error = ?,
                        last_sync_attempt = ?
                    WHERE id = ?
                    """,
                    (error[:500], time.time(), number_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error marking upload failed: {e}")

    def mark_uploaded(self, number_ids: List[int]) -> int:
        """
        Mark numbers as uploaded.

        Args:
            number_ids: List of number IDs to mark

        Returns:
            Count of updated records
        """
        if not number_ids:
            return 0
        try:
            with sqlite3.connect(self._db_path) as conn:
                placeholders = ",".join("?" * len(number_ids))
                cursor = conn.execute(
                    f"""
                    UPDATE numbers 
                    SET uploaded = 1 
                    WHERE id IN ({placeholders})
                    """,
                    number_ids,
                )
                conn.commit()
                return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Error marking uploads: {e}")
            return 0

    def backup(self) -> Optional[str]:
        """
        Create a backup of the database.

        Returns:
            Path to backup file, or None if failed
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self._backup_dir, f"numbers_backup_{timestamp}.db")

            with sqlite3.connect(self._db_path) as source:
                with sqlite3.connect(backup_path) as dest:
                    source.backup(dest)

            logger.info(f"Database backed up to: {backup_path}")
            self._rotate_backups()
            return backup_path
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None

    def _rotate_backups(self) -> None:
        """Remove backups older than retention period."""
        try:
            cutoff_time = time.time() - (settings.MAX_BACKUP_DAYS * 86400)
            for filename in os.listdir(self._backup_dir):
                if filename.endswith(".db"):
                    filepath = os.path.join(self._backup_dir, filename)
                    if os.path.getmtime(filepath) < cutoff_time:
                        os.remove(filepath)
                        logger.debug(f"Removed old backup: {filename}")
        except Exception as e:
            logger.error(f"Backup rotation error: {e}")

    def restore(self, backup_path: str) -> bool:
        """
        Restore database from backup.

        Args:
            backup_path: Path to backup file

        Returns:
            True if restored successfully
        """
        try:
            if not os.path.exists(backup_path):
                logger.error(f"Backup file not found: {backup_path}")
                return False

            current_backup = self.backup()

            shutil.copy2(backup_path, self._db_path)
            logger.info(f"Database restored from: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False

    def get_stats(self) -> dict:
        """
        Get database statistics.

        Returns:
            Dictionary with statistics
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM numbers").fetchone()[0]
                pending = conn.execute(
                    "SELECT COUNT(*) FROM numbers WHERE uploaded = 0"
                ).fetchone()[0]
                uploaded = conn.execute(
                    "SELECT COUNT(*) FROM numbers WHERE uploaded = 1"
                ).fetchone()[0]
                avg_priority = conn.execute(
                    "SELECT AVG(priority) FROM numbers"
                ).fetchone()[0] or 0

                return {
                    "total_numbers": total,
                    "pending_upload": pending,
                    "uploaded": uploaded,
                    "average_priority": round(avg_priority, 2),
                    "database_path": self._db_path,
                    "database_size_mb": round(
                        os.path.getsize(self._db_path) / 1024 / 1024, 2
                    ),
                }
        except sqlite3.Error as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}

    def get_root_breakdown(self) -> List[dict]:
        """
        Get per-root breakdown counts.

        Returns:
            List of {root, total, uploaded, pending} sorted by root
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT 
                        root,
                        COUNT(*) AS total,
                        SUM(CASE WHEN uploaded = 1 THEN 1 ELSE 0 END) AS uploaded,
                        SUM(CASE WHEN uploaded = 0 THEN 1 ELSE 0 END) AS pending
                    FROM numbers
                    GROUP BY root
                    ORDER BY root
                    """
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting root breakdown: {e}")
            return []

    def get_all_numbers_set(self) -> set:
        """
        Get a set of all number strings in the local database (for fast lookup).

        Returns:
            Set of phone number strings
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("SELECT number FROM numbers")
                return {row[0] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            logger.error(f"Error getting number set: {e}")
            return set()

    def import_numbers_from_sheet(self, numbers: List[dict]) -> dict:
        """
        Import numbers from Google Sheet into local database.
        Only inserts numbers that don't already exist locally.
        Marks them as uploaded=1 (since they're already in the sheet).

        Args:
            numbers: List of number dicts from the sheet
                     Expected keys: number, root, compound, plan, price, status

        Returns:
            {imported: int, skipped_existing: int, total_in_sheet: int}
        """
        if not numbers:
            return {"imported": 0, "skipped_existing": 0, "total_in_sheet": 0}

        imported = 0
        skipped = 0

        try:
            with sqlite3.connect(self._db_path) as conn:
                for item in numbers:
                    number = item.get("number", "").strip()
                    if not number:
                        skipped += 1
                        continue

                    # Parse root/compound, default to 0
                    root = int(item.get("root", 0) or 0)
                    compound = int(item.get("compound", 0) or 0)
                    plan = item.get("plan", "---")
                    source = item.get("source", "sheet-import")

                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO numbers 
                        (number, root, compound, type, source, found_at, priority, uploaded)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (number, root, compound, plan, source, time.time(), 0, 1),
                    )
                    if cursor.rowcount > 0:
                        imported += 1
                    else:
                        skipped += 1

                conn.commit()

            logger.info(
                f"Sheet import: {imported} new, {skipped} already existed "
                f"(total in sheet: {len(numbers)})"
            )
            return {
                "imported": imported,
                "skipped_existing": skipped,
                "total_in_sheet": len(numbers),
            }

        except sqlite3.Error as e:
            logger.error(f"Error importing numbers from sheet: {e}")
            return {"imported": imported, "skipped_existing": skipped, "total_in_sheet": len(numbers), "error": str(e)}

    def get_last_position(self) -> Optional[dict]:
        """Get the last processed record for crash recovery."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM numbers 
                    ORDER BY found_at DESC 
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting last position: {e}")
            return None

    def number_exists(self, number: str) -> bool:
        """Check if a number already exists in the database."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM numbers WHERE number = ?", (number,)
                )
                return cursor.fetchone() is not None
        except sqlite3.Error:
            return False

    def delete_number(self, number: str) -> bool:
        """
        Delete a number from the database.

        Args:
            number: Phone number to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM numbers WHERE number = ?", (number,)
                )
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Number deleted: {number}")
                    return True
                else:
                    logger.debug(f"Number not found for deletion: {number}")
                    return False
        except sqlite3.Error as e:
            logger.error(f"Error deleting number: {e}")
            return False

    def delete_unavailable_numbers(self, unavailable: List[str]) -> int:
        """
        Batch delete unavailable numbers from the database.

        Args:
            unavailable: List of phone numbers to delete

        Returns:
            Count of successfully deleted numbers
        """
        deleted = 0
        for number in unavailable:
            if self.delete_number(number):
                deleted += 1
        if deleted > 0:
            logger.info(f"Deleted {deleted} unavailable numbers from backup")
        return deleted
