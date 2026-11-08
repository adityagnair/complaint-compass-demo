import csv
from datetime import datetime, timedelta, timezone
from io import StringIO

from fastapi import APIRouter
from fastapi.responses import Response

from backend.database import database

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
def overview():
    with database() as connection:
        row = connection.execute(
            """SELECT COUNT(*) AS complaint_count,
                      COUNT(DISTINCT customer_id) AS affected_customers,
                      SUM(CASE WHEN severity >= 4 THEN 1 ELSE 0 END) AS high_severity_count,
                      COUNT(DISTINCT channel) AS channel_count
               FROM complaints"""
        ).fetchone()
        customer_count = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        channel_counts = connection.execute("SELECT channel, COUNT(*) AS count FROM complaints GROUP BY channel").fetchall()
        critical_issues = connection.execute(
            """SELECT COUNT(*) FROM issue_clusters WHERE run_id =
               (SELECT run_id FROM analysis_runs ORDER BY created_at DESC, run_id DESC LIMIT 1)
               AND average_severity >= 4"""
        ).fetchone()[0]
    return {
        **dict(row),
        "high_severity_count": row["high_severity_count"] or 0,
        "customer_count": customer_count,
        "critical_issue_count": critical_issues,
        "channel_counts": {item["channel"]: item["count"] for item in channel_counts},
    }


@router.get("/trends")
def trends():
    with database() as connection:
        monthly = connection.execute(
            """SELECT substr(CAST(submitted_at AS TEXT), 1, 7) AS month, COUNT(*) AS count
               FROM complaints WHERE submitted_at IS NOT NULL AND length(CAST(submitted_at AS TEXT)) >= 7
               GROUP BY substr(CAST(submitted_at AS TEXT), 1, 7) ORDER BY month"""
        ).fetchall()
        rows = connection.execute(
            """SELECT issue_clusters.label, complaints.submitted_at
               FROM complaints JOIN issue_clusters ON issue_clusters.cluster_id = complaints.issue_cluster_id
               WHERE complaints.duplicate_of IS NULL"""
        ).fetchall()

    now = datetime.now(timezone.utc)
    recent, previous = {}, {}
    for row in rows:
        try:
            submitted = datetime.fromisoformat(str(row["submitted_at"]).replace("Z", "+00:00"))
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        age = now - submitted.astimezone(timezone.utc)
        if timedelta(0) <= age <= timedelta(days=30):
            recent[row["label"]] = recent.get(row["label"], 0) + 1
        elif timedelta(days=30) < age <= timedelta(days=60):
            previous[row["label"]] = previous.get(row["label"], 0) + 1
    emerging = [
        {"label": label, "recent_reports": count, "previous_reports": previous.get(label, 0), "change": count - previous.get(label, 0)}
        for label, count in recent.items()
    ]
    emerging.sort(key=lambda item: (-item["change"], -item["recent_reports"], item["label"]))
    return {"monthly": [dict(row) for row in monthly], "emerging_issues": emerging[:10]}


@router.get("/segments")
def customer_segments():
    with database() as connection:
        rows = connection.execute(
            """SELECT customers.customer_id, customers.country, customers.state, customers.age_group,
                      customers.student_status, customers.income_bracket, COUNT(complaints.id) AS complaint_count
               FROM customers LEFT JOIN complaints USING (customer_id)
               GROUP BY customers.id ORDER BY customers.customer_id"""
        ).fetchall()
    return {"total": len(rows), "items": [dict(row) for row in rows]}


@router.get("/report.csv")
def export_report_csv():
    with database() as connection:
        rows = connection.execute(
            """SELECT complaints.complaint_id, complaints.customer_id, complaints.complaint_text,
                      complaints.channel, complaints.submitted_at, complaints.severity,
                      complaints.duplicate_of, customers.country, customers.state, customers.age_group,
                      customers.student_status, customers.income_bracket, issue_clusters.label AS issue_label,
                      issue_clusters.priority_score
               FROM complaints LEFT JOIN customers USING (customer_id)
               LEFT JOIN issue_clusters ON issue_clusters.cluster_id = complaints.issue_cluster_id
               ORDER BY complaints.submitted_at DESC"""
        ).fetchall()
    output = StringIO()
    fields = ["complaint_id", "customer_id", "complaint_text", "channel", "submitted_at", "severity", "duplicate_of", "country", "state", "age_group", "student_status", "income_bracket", "issue_label", "priority_score"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(dict(row) for row in rows)
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=complaint-compass-report.csv"})
