import csv
import io
from pathlib import Path


def test_upload_persists_customer_segments_and_csv_report(client):
    content = (
        "complaint_id,customer_id,complaint_text,channel,severity,country,state,age_group,student_status,income_bracket\n"
        "C-1,U-1,Payment deducted twice,email,5,India,Delhi,18-24,yes,under-300000\n"
        "C-2,U-2,Delivery was late,voice,2,India,Karnataka,25-34,no,300000-700000\n"
    )
    response = client.post("/api/complaints/upload", files={"file": ("input.csv", content, "text/csv")})

    assert response.status_code == 200
    assert response.json()["added"] == 2
    assert response.json()["skipped"] == 0

    segments = client.get("/api/analytics/segments").json()
    assert segments["total"] == 2
    assert {item["country"] for item in segments["items"]} == {"India"}
    assert {item["student_status"] for item in segments["items"]} == {"yes", "no"}

    report = client.get("/api/analytics/report.csv")
    rows = list(csv.DictReader(io.StringIO(report.text)))
    assert report.status_code == 200
    assert {row["complaint_id"] for row in rows} == {"C-1", "C-2"}
    assert "complaint-compass-report.csv" in report.headers["content-disposition"]


def test_documented_api_aliases_and_compatibility_views(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/issues/top10").json()["items"] == []
    response = client.post("/api/complaints/analyze", json={})
    assert response.status_code == 400
    assert "before running analysis" in response.json()["detail"]

    from backend.database import database

    with database() as connection:
        for name in ("clusters", "complaint_clusters", "benchmark_runs", "issue_scores"):
            assert connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] == 0


def test_authenticated_channel_intake_normalizes_and_deduplicates_events(client, monkeypatch):
    monkeypatch.setenv("INTAKE_WEBHOOK_TOKEN", "test-intake-secret")
    events = {
        "email": {"MessageID": "mail-1", "From": "person@example.com", "Subject": "Refund", "TextBody": "My refund has not arrived."},
        "voice": {"CallSid": "call-1", "From": "+15550001", "SpeechResult": "The delivery never arrived."},
        "chatbot": {"message_id": "chat-1", "user_id": "customer-1", "message": "The app crashes during payment."},
        "social": {"post_id": "social-1", "author_id": "social-user-1", "text": "I cannot access my account."},
    }

    for channel, payload in events.items():
        response = client.post(
            f"/api/intake/{channel}",
            json=payload,
            headers={"Authorization": "Bearer test-intake-secret"},
        )
        assert response.status_code == 202, f"{channel}: {response.text}"
        assert response.json()["status"] == "accepted"
        retry = client.post(
            f"/api/intake/{channel}",
            json=payload,
            headers={"X-Intake-Token": "test-intake-secret"},
        )
        assert retry.status_code == 202
        assert retry.json()["status"] == "duplicate"

    complaints = client.get("/api/complaints", params={"limit": 20}).json()["items"]
    assert {item["channel"] for item in complaints} == set(events)
    assert len(complaints) == len(events)


def test_channel_intake_requires_secret_and_voice_transcript(client, monkeypatch):
    monkeypatch.setenv("INTAKE_WEBHOOK_TOKEN", "test-intake-secret")
    unauthorized = client.post("/api/intake/chatbot", json={"text": "Help me with payment"})
    assert unauthorized.status_code == 401

    no_transcript = client.post(
        "/api/intake/voice",
        json={"call_sid": "call-without-transcript"},
        headers={"X-Intake-Token": "test-intake-secret"},
    )
    assert no_transcript.status_code == 422


def test_unified_intake_webhook_uses_channel_in_payload(client, monkeypatch):
    monkeypatch.setenv("INTAKE_WEBHOOK_TOKEN", "test-intake-secret")
    response = client.post(
        "/api/intake",
        json={"channel": "social", "post_id": "post-unified-1", "author_id": "social-user", "text": "My account was locked without warning."},
        headers={"X-Intake-Token": "test-intake-secret"},
    )
    assert response.status_code == 202
    assert response.json()["channel"] == "social"
    stored = client.get("/api/complaints", params={"channel": "social"}).json()["items"]
    assert stored[0]["complaint_text"] == "My account was locked without warning."


def test_same_customer_repeat_linking_is_independent_of_channel():
    import numpy as np

    from backend.ai.pipeline import _find_duplicates

    records = [
        {"customer_id": "U-1", "submitted_at": "2026-10-01T10:00:00+00:00", "channel": "email"},
        {"customer_id": "U-1", "submitted_at": "2026-10-02T10:00:00+00:00", "channel": "chatbot"},
        {"customer_id": "U-2", "submitted_at": "2026-10-02T10:00:00+00:00", "channel": "voice"},
    ]
    embeddings = np.asarray([[1.0, 0.0], [0.999, 0.001], [1.0, 0.0]], dtype=np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)

    assert _find_duplicates(records, embeddings, threshold=0.92, window_days=30) == {1: 0}


def test_full_sample_import_analysis_and_reporting_workflow(client):
    sample = Path(__file__).resolve().parents[1] / "dataset" / "complaints.csv"
    with sample.open("rb") as file:
        uploaded = client.post(
            "/api/complaints/upload",
            files={"file": ("complaints.csv", file.read(), "text/csv")},
        )
    assert uploaded.status_code == 200
    assert uploaded.json()["added"] == 6
    assert uploaded.json()["skipped"] == 0

    analysis = client.post("/api/complaints/analyze", json={
        "min_cluster_size": 2,
        "duplicate_similarity_threshold": 0.92,
        "duplicate_window_days": 30,
    })
    assert analysis.status_code == 200, analysis.text
    result = analysis.json()
    assert result["complaints_processed"] == 6
    assert result["duplicate_submissions"] == 1
    assert result["issues_found"] >= 1
    assert all("priority_score" in issue for issue in result["clusters"])

    ranked = client.get("/api/issues/top10")
    assert ranked.status_code == 200
    assert ranked.json()["total_issues"] == result["issues_found"]
    assert len(ranked.json()["items"]) <= 10
    detail = client.get(f"/api/issues/{ranked.json()['items'][0]['cluster_id']}")
    assert detail.status_code == 200
    assert len(detail.json()["complaints"]) == detail.json()["issue"]["submission_count"]

    overview = client.get("/api/analytics/overview").json()
    assert overview["complaint_count"] == 6
    assert overview["affected_customers"] == 4
    trend = client.get("/api/analytics/trends").json()
    assert sum(item["count"] for item in trend["monthly"]) == 6
    assert client.get("/api/analytics/segments").json()["total"] == 4
    email_filter = client.get("/api/complaints", params={"channel": "email"}).json()
    assert email_filter["total"] == 2
    export = client.get("/api/analytics/report.csv")
    assert len(list(csv.DictReader(io.StringIO(export.text)))) == 6
