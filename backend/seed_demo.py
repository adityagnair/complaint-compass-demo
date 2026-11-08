"""Load the repository's synthetic sample data and precompute its analysis."""

import os
from pathlib import Path

from backend.database import database, initialize_database
from backend.routes.complaints import insert_complaint
from backend.services.complaints import parse_csv

DATASET = Path(__file__).resolve().parents[1] / "dataset" / "complaints.csv"


def seed_demo() -> None:
    initialize_database()
    rows, errors = parse_csv(DATASET.read_bytes())
    if errors:
        raise RuntimeError(f"Sample CSV contains invalid rows: {errors}")

    expected_ids = {complaint.complaint_id for _, complaint in rows}
    with database() as connection:
        existing = {row[0] for row in connection.execute("SELECT complaint_id FROM complaints").fetchall()}
        if not existing.issubset(expected_ids):
            raise RuntimeError("Refusing to seed: database contains records outside the synthetic sample set")
        for _, complaint in rows:
            insert_complaint(connection, complaint)
        has_analysis = connection.execute("SELECT 1 FROM analysis_runs LIMIT 1").fetchone() is not None

    if not has_analysis:
        os.environ["OLLAMA_LABELS"] = "false"
        from backend.ai.pipeline import run_analysis

        run_analysis()
    print(f"Demo dataset ready: {len(rows)} synthetic complaints and a precomputed analysis")


if __name__ == "__main__":
    seed_demo()
