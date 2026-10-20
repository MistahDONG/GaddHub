import sqlite3
import time
from pathlib import Path


class Store:
    """Used exclusively by the sync thread; acknowledgements survive restarts."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS uploads (
                destination TEXT NOT NULL,
                hash TEXT NOT NULL,
                payload BLOB,
                state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0,
                error TEXT,
                acknowledged_at REAL,
                source_name TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (destination, hash)
            );
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(uploads)")}
        if "source_name" not in columns:
            self.db.execute("ALTER TABLE uploads ADD COLUMN source_name TEXT NOT NULL DEFAULT ''")
        self.db.commit()

    def enqueue(
        self, destination: str, content_hash: str, payload: bytes, source_name: str = ""
    ) -> bool:
        size = self.db.execute("SELECT COALESCE(SUM(length(payload)), 0) FROM uploads").fetchone()[
            0
        ]
        exists = self.db.execute(
            "SELECT 1 FROM uploads WHERE destination=? AND hash=?", (destination, content_hash)
        ).fetchone()
        if not exists and size + len(payload) > 128 * 1024 * 1024:
            raise ValueError(
                "Local queue is full (128 MiB); uploads must succeed before reading more."
            )
        cursor = self.db.execute(
            """INSERT OR IGNORE INTO uploads (destination, hash, payload, source_name)
               VALUES (?, ?, ?, ?)""",
            (destination, content_hash, payload, source_name),
        )
        inserted = cursor.rowcount == 1
        if not inserted and source_name:
            self.db.execute(
                """UPDATE uploads SET source_name=?
                   WHERE destination=? AND hash=? AND source_name=''""",
                (source_name, destination, content_hash),
            )
        self.db.commit()
        return inserted

    def source_name(self, destination: str, content_hash: str) -> str:
        row = self.db.execute(
            "SELECT source_name FROM uploads WHERE destination=? AND hash=?",
            (destination, content_hash),
        ).fetchone()
        return row[0] if row is not None else ""

    def due(self, destination: str) -> tuple[str, bytes, int] | None:
        return self.db.execute(
            """SELECT hash, payload, attempts FROM uploads
               WHERE destination=? AND state='pending' AND next_attempt<=?
               ORDER BY rowid LIMIT 1""",
            (destination, time.time()),
        ).fetchone()

    def acknowledge(self, destination: str, content_hash: str) -> None:
        self.db.execute(
            """UPDATE uploads SET state='sent', payload=NULL, error=NULL, acknowledged_at=?
               WHERE destination=? AND hash=?""",
            (time.time(), destination, content_hash),
        )
        self.db.commit()

    def fail(
        self,
        destination: str,
        content_hash: str,
        attempts: int,
        delay: float,
        message: str,
        permanent: bool,
    ) -> None:
        self.db.execute(
            """UPDATE uploads SET attempts=?, next_attempt=?, error=?, state=?
               WHERE destination=? AND hash=?""",
            (
                attempts,
                time.time() + delay,
                message,
                "rejected" if permanent else "pending",
                destination,
                content_hash,
            ),
        )
        self.db.commit()

    def retry(self, destination: str) -> None:
        self.db.execute(
            """UPDATE uploads SET state='pending', next_attempt=0
               WHERE destination=? AND state!='sent'""",
            (destination,),
        )
        self.db.commit()

    def status(self, destination: str) -> tuple[int, int, float | None]:
        row = self.db.execute(
            """SELECT COALESCE(SUM(state='pending'), 0), COALESCE(SUM(state='rejected'), 0),
                      MAX(acknowledged_at) FROM uploads WHERE destination=?""",
            (destination,),
        ).fetchone()
        return row[0], row[1], row[2]

    def close(self) -> None:
        self.db.close()
