"""SQLite persistence (stdlib sqlite3; no ORM needed for three tables).
Complex values (extraction, decision, ...) are stored as JSON text and always
re-validated through the Pydantic models on read."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional

from backend.models import Complaint, Draft, Session

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL,          -- Session JSON (photo_paths are relative names)
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    created_at TEXT NOT NULL,
    data TEXT NOT NULL           -- Draft JSON
);
CREATE TABLE IF NOT EXISTS complaints (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES drafts(id),
    route TEXT NOT NULL,
    category TEXT NOT NULL,
    location_text TEXT,
    ward TEXT,
    filed_on TEXT NOT NULL,
    due_on TEXT NOT NULL,
    status TEXT NOT NULL,
    parent_complaint_id TEXT REFERENCES complaints(id),
    escalation_level INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_complaints_category ON complaints(category, status);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """One transaction per block: commit on success, roll back on error."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    # -- sessions ---------------------------------------------------------
    def save_session(self, s: Session) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, created_at, data, status) VALUES (?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, status=excluded.status",
                (s.id, datetime.now().isoformat(), s.model_dump_json(), s.status),
            )

    def get_session(self, session_id: str) -> Optional[Session]:
        with self.connect() as conn:
            row = conn.execute("SELECT data FROM sessions WHERE id=?", (session_id,)).fetchone()
        return Session.model_validate_json(row["data"]) if row else None

    # -- drafts -----------------------------------------------------------
    def save_draft(self, d: Draft) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO drafts (id, session_id, created_at, data) VALUES (?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (d.id, d.session_id, d.created_at.isoformat(), d.model_dump_json()),
            )

    def get_draft(self, draft_id: str) -> Optional[Draft]:
        with self.connect() as conn:
            row = conn.execute("SELECT data FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return Draft.model_validate_json(row["data"]) if row else None

    # -- complaints -------------------------------------------------------
    @staticmethod
    def _complaint(row: sqlite3.Row) -> Complaint:
        return Complaint(**{k: row[k] for k in row.keys()})

    def save_complaint(self, c: Complaint) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO complaints (id, draft_id, route, category, location_text, ward, "
                "filed_on, due_on, status, parent_complaint_id, escalation_level) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, due_on=excluded.due_on",
                (c.id, c.draft_id, c.route, c.category, c.location_text, c.ward,
                 c.filed_on.isoformat(), c.due_on.isoformat(), c.status,
                 c.parent_complaint_id, c.escalation_level),
            )

    def get_complaint(self, complaint_id: str) -> Optional[Complaint]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()
        return self._complaint(row) if row else None

    def get_complaint_for_draft(self, draft_id: str) -> Optional[Complaint]:
        """The complaint filed from this draft, if any (a draft is filed once)."""
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM complaints WHERE draft_id=? ORDER BY id LIMIT 1",
                               (draft_id,)).fetchone()
        return self._complaint(row) if row else None

    def list_complaints(self) -> list[Complaint]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM complaints ORDER BY filed_on DESC, id").fetchall()
        return [self._complaint(r) for r in rows]

    def open_complaints_for_category(self, category: str) -> list[Complaint]:
        """Candidates for routing history; location matching is done by the
        routing module."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM complaints WHERE category=? AND status IN ('filed','overdue')",
                (category,),
            ).fetchall()
        return [self._complaint(r) for r in rows]

    def mark_overdue(self, today: date) -> int:
        """Persist the computed overdue state (D7); returns rows changed."""
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE complaints SET status='overdue' WHERE status='filed' AND due_on < ?",
                (today.isoformat(),),
            )
            return cur.rowcount
