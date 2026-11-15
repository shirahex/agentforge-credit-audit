"""SQLite access shared by the case store and the run store (tasks I3 and I4).

One database file, `audit.sqlite`, under config.DATA_DIR. Every operation
opens its own short connection: the API serves requests from several
threads while audits run in background threads, and SQLite connections are
not meant to be shared between threads. WAL mode lets readers (the event
stream) work while a run is writing.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    applicant_id TEXT NOT NULL,
    application  TEXT NOT NULL,
    status       TEXT NOT NULL,            -- running | awaiting_review | finished | error
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    decision     TEXT,
    review       TEXT,
    error        TEXT
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    seq    INTEGER NOT NULL,
    body   TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS cases (
    run_id              TEXT PRIMARY KEY,
    applicant_id        TEXT NOT NULL,
    closed_at           TEXT NOT NULL,
    decision            TEXT NOT NULL,
    final_outcome       TEXT NOT NULL,
    default_probability REAL NOT NULL,
    escalated           INTEGER NOT NULL,
    reviewed            INTEGER NOT NULL,
    attempts            INTEGER NOT NULL,
    paths               INTEGER NOT NULL,
    best_path           TEXT NOT NULL,
    model_version       TEXT NOT NULL,
    application         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_started ON runs (started_at);
"""
_ready: set[str] = set()


def data_dir(*parts: str) -> Path:
    path = Path(config.DATA_DIR).joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_file() -> Path:
    return data_dir() / "audit.sqlite"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    file = database_file()
    conn = sqlite3.connect(file, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        if str(file) not in _ready:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            _ready.add(str(file))
        yield conn
        conn.commit()
    finally:
        conn.close()
