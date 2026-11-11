import json

import numpy as np

from backend.ai import pipeline, severity
from backend import database as database_module
from backend.database import database, initialize_database
from backend.models.schemas import ComplaintCreate
from backend.routes.complaints import insert_complaint


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.value).encode()


def test_ollama_severity_accepts_only_requested_ids_and_valid_scores(monkeypatch):
    monkeypatch.setenv("OLLAMA_SEVERITY", "true")
    monkeypatch.setattr(
        severity,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse({"response": json.dumps({"severities": [
            {"complaint_id": "c-1", "severity": 5},
            {"complaint_id": "c-2", "severity": 9},
            {"complaint_id": "other", "severity": 1},
        ]})}),
    )

    scores, model = severity.assess_missing_severities([
        {"complaint_id": "c-1", "complaint_text": "A safety issue"},
        {"complaint_id": "c-2", "complaint_text": "A small delay"},
    ])

    assert scores == {"c-1": 5}
    assert model == "qwen2.5:3b"


def test_ollama_severity_can_be_disabled(monkeypatch):
    monkeypatch.setenv("OLLAMA_SEVERITY", "false")

    scores, model = severity.assess_missing_severities([
        {"complaint_id": "c-1", "complaint_text": "A complaint"},
    ])

    assert scores == {}
    assert model is None


def test_analysis_persists_ollama_severity_and_uses_it_in_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_engine", None)
    monkeypatch.setattr(database_module, "DATABASE_URL", "")
    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "severity-test.db")
    initialize_database()
    for index in range(2):
        with database() as connection:
            insert_complaint(connection, ComplaintCreate(
                complaint_id=f"auto-severity-{index}",
                customer_id=f"customer-{index}",
                complaint_text=f"Service complaint number {index}",
            ))

    monkeypatch.setattr(pipeline, "embed_texts", lambda texts: np.tile(
        np.array([[1.0] + [0.0] * 383], dtype=np.float32), (len(texts), 1)
    ))
    monkeypatch.setattr(pipeline, "cluster_embeddings", lambda embeddings, _size: np.zeros(len(embeddings), dtype=int))
    monkeypatch.setattr(pipeline, "label_clusters", lambda _clusters: ({0: ("Service issues", "test")}, "test-labeler"))
    monkeypatch.setattr(pipeline, "assess_missing_severities", lambda records: (
        {item["complaint_id"]: 4 for item in records}, "test-ollama"
    ))

    result = pipeline.run_analysis()

    assert result["severity_model"] == "test-ollama"
    assert result["clusters"][0]["average_severity"] == 4
    assert result["clusters"][0]["priority_score"] == 87.5
    with database() as connection:
        sources = connection.execute(
            "SELECT severity_source FROM complaints ORDER BY complaint_id"
        ).fetchall()
    assert [row["severity_source"] for row in sources] == ["ollama", "ollama"]
