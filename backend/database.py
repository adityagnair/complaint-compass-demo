import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = Path(os.getenv("COMPLAINT_COMPASS_DB", BACKEND_DIR / "data" / "complaint_compass.db"))
if not DB_PATH.is_absolute():
    DB_PATH = BACKEND_DIR / DB_PATH


class HybridRow(dict):
    """Mapping row that also preserves sqlite3.Row-style numeric indexing."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class SQLResult:
    def __init__(self, result):
        self.result = result

    @staticmethod
    def _wrap(row):
        return HybridRow(row._mapping)

    def fetchone(self):
        row = self.result.fetchone()
        return self._wrap(row) if row is not None else None

    def fetchall(self):
        return [self._wrap(row) for row in self.result.fetchall()]

    @property
    def rowcount(self):
        return self.result.rowcount


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement: str, parameters=()):
        from sqlalchemy import text

        if not parameters:
            # DDL and simple queries often contain colons in string literals;
            # pass them through unchanged instead of parsing bind syntax.
            return SQLResult(self.connection.exec_driver_sql(statement))
        names = iter(range(len(parameters)))
        sql = re.sub(r"\?", lambda _: f":p{next(names)}", statement)
        bindings = {f"p{i}": value for i, value in enumerate(parameters)}
        return SQLResult(self.connection.execute(text(sql), bindings))

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                # DDL scripts contain quoted literals (including JSON defaults)
                # with colons. Sending those through SQLAlchemy's text() parser
                # can mistake the literal colons for bind parameters.
                self.connection.exec_driver_sql(statement)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def _postgres_engine():
    from sqlalchemy import create_engine

    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if "sslmode=" not in url:
        url += "&sslmode=require" if "?" in url else "?sslmode=require"
    # Supabase's transaction pooler can reuse server connections across client
    # sessions; disabling psycopg prepared statements avoids name collisions.
    return create_engine(url, connect_args={"prepare_threshold": None}, pool_pre_ping=True)


_engine = _postgres_engine() if DATABASE_URL else None


def connect():
    if _engine is not None:
        return PostgresConnection(_engine.connect())
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database() -> Iterator[sqlite3.Connection | PostgresConnection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with database() as connection:
        schema = """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL UNIQUE,
            country TEXT,
            state TEXT,
            age_group TEXT,
            student_status TEXT,
            income_bracket TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT NOT NULL UNIQUE,
            customer_id TEXT,
            complaint_text TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'other',
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            severity INTEGER NOT NULL DEFAULT 3 CHECK (severity BETWEEN 1 AND 5),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON UPDATE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_complaints_customer ON complaints(customer_id);
        CREATE INDEX IF NOT EXISTS idx_complaints_submitted ON complaints(submitted_at);
        """
        if _engine is None:
            connection.executescript(schema)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(complaints)").fetchall()}
            for column, data_type in (
                ("normalized_text", "TEXT"),
                ("embedding", "TEXT"),
                ("embedding_model", "TEXT"),
                ("issue_cluster_id", "TEXT"),
                ("duplicate_of", "TEXT"),
            ):
                if column not in columns:
                    connection.execute(f"ALTER TABLE complaints ADD COLUMN {column} {data_type}")
        else:
            postgres_schema = (
                schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
                .replace("created_at TEXT NOT NULL", "created_at TIMESTAMPTZ NOT NULL")
                .replace("submitted_at TEXT NOT NULL", "submitted_at TIMESTAMPTZ NOT NULL")
            )
            connection.executescript(postgres_schema)
            for column, data_type in (
                ("normalized_text", "TEXT"),
                ("embedding", "TEXT"),
                ("embedding_model", "TEXT"),
                ("issue_cluster_id", "TEXT"),
                ("duplicate_of", "TEXT"),
            ):
                connection.execute(f"ALTER TABLE complaints ADD COLUMN IF NOT EXISTS {column} {data_type}")
        analysis_schema = """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            embedding_model TEXT NOT NULL,
            clustering_method TEXT NOT NULL,
            min_cluster_size INTEGER NOT NULL,
            duplicate_similarity_threshold REAL NOT NULL,
            duplicate_window_days INTEGER NOT NULL,
            complaints_processed INTEGER NOT NULL,
            issues_found INTEGER NOT NULL,
            label_model TEXT,
            scoring_formula TEXT NOT NULL DEFAULT 'Priority = 0.4S + 0.3F + 0.3I',
            scoring_weights TEXT NOT NULL DEFAULT '{"severity":0.4,"frequency":0.3,"impact":0.3}',
            severity_normalization TEXT NOT NULL DEFAULT 'S = ((average severity on 1–5 scale - 1) / 4) × 100',
            relative_normalization TEXT NOT NULL DEFAULT 'F and I = (issue value / maximum value in this analysis run) × 100',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS issue_clusters (
            cluster_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            label TEXT NOT NULL,
            label_source TEXT NOT NULL,
            representative_text TEXT NOT NULL,
            complaint_count INTEGER NOT NULL,
            submission_count INTEGER NOT NULL DEFAULT 0,
            affected_customers INTEGER NOT NULL,
            duplicate_count INTEGER NOT NULL,
            average_severity REAL NOT NULL,
            severity_score REAL NOT NULL DEFAULT 0,
            frequency_score REAL NOT NULL DEFAULT 0,
            impact_score REAL NOT NULL DEFAULT 0,
            priority_score REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_complaints_cluster ON complaints(issue_cluster_id);
        CREATE INDEX IF NOT EXISTS idx_clusters_run ON issue_clusters(run_id);
        """
        if _engine is None:
            connection.executescript(analysis_schema)
            run_columns = {row[1] for row in connection.execute("PRAGMA table_info(analysis_runs)").fetchall()}
            for column, definition in (
                ("scoring_formula", "TEXT NOT NULL DEFAULT 'Priority = 0.4S + 0.3F + 0.3I'"),
                ("scoring_weights", "TEXT NOT NULL DEFAULT '{\"severity\":0.4,\"frequency\":0.3,\"impact\":0.3}'"),
                ("severity_normalization", "TEXT NOT NULL DEFAULT 'S = ((average severity on 1–5 scale - 1) / 4) × 100'"),
                ("relative_normalization", "TEXT NOT NULL DEFAULT 'F and I = (issue value / maximum value in this analysis run) × 100'"),
            ):
                if column not in run_columns:
                    connection.execute(f"ALTER TABLE analysis_runs ADD COLUMN {column} {definition}")
            cluster_columns = {row[1] for row in connection.execute("PRAGMA table_info(issue_clusters)").fetchall()}
            for column, definition in (
                ("submission_count", "INTEGER NOT NULL DEFAULT 0"),
                ("severity_score", "REAL NOT NULL DEFAULT 0"),
                ("frequency_score", "REAL NOT NULL DEFAULT 0"),
                ("impact_score", "REAL NOT NULL DEFAULT 0"),
                ("priority_score", "REAL NOT NULL DEFAULT 0"),
            ):
                if column not in cluster_columns:
                    connection.execute(f"ALTER TABLE issue_clusters ADD COLUMN {column} {definition}")
        else:
            postgres_analysis_schema = analysis_schema.replace("created_at TEXT NOT NULL", "created_at TIMESTAMPTZ NOT NULL")
            connection.executescript(postgres_analysis_schema)
            for column, definition in (
                ("scoring_formula", "TEXT NOT NULL DEFAULT 'Priority = 0.4S + 0.3F + 0.3I'"),
                ("scoring_weights", "TEXT NOT NULL DEFAULT '{\"severity\":0.4,\"frequency\":0.3,\"impact\":0.3}'"),
                ("severity_normalization", "TEXT NOT NULL DEFAULT 'S = ((average severity on 1–5 scale - 1) / 4) × 100'"),
                ("relative_normalization", "TEXT NOT NULL DEFAULT 'F and I = (issue value / maximum value in this analysis run) × 100'"),
            ):
                connection.execute(f"ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS {column} {definition}")
            for column, definition in (
                ("submission_count", "INTEGER NOT NULL DEFAULT 0"),
                ("severity_score", "REAL NOT NULL DEFAULT 0"),
                ("frequency_score", "REAL NOT NULL DEFAULT 0"),
                ("impact_score", "REAL NOT NULL DEFAULT 0"),
                ("priority_score", "REAL NOT NULL DEFAULT 0"),
            ):
                connection.execute(f"ALTER TABLE issue_clusters ADD COLUMN IF NOT EXISTS {column} {definition}")

        # Public schema aliases preserve the project's established storage while
        # exposing the logical Phase 6 table names for integrations and exports.
        compatibility_views = {
            "clusters": """SELECT cluster_id, run_id, label, label_source, representative_text,
                complaint_count, submission_count, affected_customers, duplicate_count, average_severity,
                severity_score, frequency_score, impact_score, priority_score, created_at FROM issue_clusters""",
            "complaint_clusters": """SELECT complaint_id, issue_cluster_id AS cluster_id, duplicate_of
                FROM complaints WHERE issue_cluster_id IS NOT NULL""",
            "benchmark_runs": """SELECT run_id AS benchmark_run_id, embedding_model, clustering_method,
                min_cluster_size, duplicate_similarity_threshold, duplicate_window_days,
                complaints_processed, issues_found, label_model, scoring_formula, scoring_weights,
                created_at FROM analysis_runs""",
            "issue_scores": """SELECT cluster_id, run_id, severity_score, frequency_score, impact_score,
                priority_score FROM issue_clusters""",
        }
        if _engine is None:
            for name, query in compatibility_views.items():
                connection.execute(f"CREATE VIEW IF NOT EXISTS {name} AS {query}")
        else:
            for name, query in compatibility_views.items():
                exists = connection.execute("SELECT to_regclass(?)", (name,)).fetchone()[0]
                if not exists:
                    connection.execute(f"CREATE VIEW {name} AS {query}")
