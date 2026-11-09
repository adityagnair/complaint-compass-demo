from fastapi import APIRouter, HTTPException, Query

from backend.database import database
from backend.models.schemas import IssueWorkflowUpdate
from backend.services.issue_workflow import issue_key, workflow_for_label
from backend.services.prioritization import score_issues

router = APIRouter(prefix="/api/issues", tags=["issues"])
LOW_COHESION_REVIEW_THRESHOLD = 65.0


@router.get("/top10")
@router.get("")
def list_issues(
    limit: int = Query(default=10, ge=1, le=200),
    country: str | None = Query(default=None, max_length=100),
    state: str | None = Query(default=None, max_length=100),
    age_group: str | None = Query(default=None, max_length=40),
    student_status: str | None = Query(default=None, max_length=40),
    income_bracket: str | None = Query(default=None, max_length=100),
):
    with database() as connection:
        latest_run = connection.execute(
            "SELECT * FROM analysis_runs ORDER BY created_at DESC, run_id DESC LIMIT 1"
        ).fetchone()
        if latest_run is None:
            total_reports = connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
            return {"latest_analysis": None, "items": [], "total_issues": 0, "unclustered_count": total_reports, "duplicate_submissions": 0, "analysis_stale": total_reports > 0, "new_since_analysis": total_reports}
        clusters = connection.execute(
            "SELECT * FROM issue_clusters WHERE run_id = ? ORDER BY label", (latest_run["run_id"],)
        ).fetchall()
        filter_values = {
            "country": country, "state": state, "age_group": age_group,
            "student_status": student_status, "income_bracket": income_bracket,
        }
        conditions = []
        filter_params: list[object] = []
        for column, value in filter_values.items():
            if value:
                conditions.append(f"customers.{column} = ?")
                filter_params.append(value)
        cohort_where = " AND ".join(conditions)
        cluster_ids = [item["cluster_id"] for item in clusters]
        rows = []
        if cluster_ids:
            cluster_placeholders = ", ".join("?" for _ in cluster_ids)
            conditions_sql = f" AND {cohort_where}" if cohort_where else ""
            rows = connection.execute(
                f"""SELECT complaints.complaint_id, complaints.customer_id, complaints.complaint_text,
                          complaints.severity, complaints.severity_source, complaints.duplicate_of, complaints.issue_cluster_id,
                          customers.country, customers.state, customers.age_group,
                          customers.student_status, customers.income_bracket
                   FROM complaints LEFT JOIN customers USING (customer_id)
                   WHERE complaints.issue_cluster_id IN ({cluster_placeholders}){conditions_sql}""",
                [*cluster_ids, *filter_params],
            ).fetchall()
        grouped: dict[str, list[dict]] = {item["cluster_id"]: [] for item in clusters}
        for row in rows:
            grouped[row["issue_cluster_id"]].append(dict(row))

        items = []
        for cluster in clusters:
            evidence = grouped[cluster["cluster_id"]]
            primary = [item for item in evidence if item["duplicate_of"] is None]
            if not primary:
                continue
            item = dict(cluster)
            item["complaint_count"] = len(primary)
            item["submission_count"] = len(evidence)
            item["duplicate_count"] = len(evidence) - len(primary)
            item["affected_customers"] = len({row["customer_id"] for row in primary if row["customer_id"]})
            known_severities = [row["severity"] for row in primary if row["severity_source"] == "provided"]
            item["severity_coverage"] = len(known_severities) / len(primary) if primary else 0.0
            item["severity_missing_count"] = len(primary) - len(known_severities)
            item["average_severity"] = round(sum(known_severities) / len(known_severities), 2) if known_severities else None
            item["needs_review"] = float(item.get("cohesion_score") or 0) < LOW_COHESION_REVIEW_THRESHOLD
            items.append(item)
            item["workflow"] = workflow_for_label(connection, item["label"])
        score_issues(items)
        items.sort(key=lambda item: (-item["priority_score"], -item["affected_customers"], -item["complaint_count"]))
        total_issues = len(items)
        duplicates = sum(item["duplicate_count"] for item in items)
        unclustered = connection.execute(
            """SELECT COUNT(*) FROM complaints LEFT JOIN customers USING (customer_id)
               WHERE complaints.issue_cluster_id IS NULL AND complaints.duplicate_of IS NULL"""
            + (f" AND {cohort_where}" if cohort_where else ""),
            filter_params,
        ).fetchone()[0]
        matched_customers = connection.execute(
            """SELECT COUNT(DISTINCT complaints.customer_id) FROM complaints
               LEFT JOIN customers USING (customer_id) WHERE complaints.customer_id IS NOT NULL"""
            + (f" AND {cohort_where}" if cohort_where else ""),
            filter_params,
        ).fetchone()[0]
        total_reports = connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        new_since_analysis = max(0, total_reports - int(latest_run["complaints_processed"]))
    return {
        "latest_analysis": dict(latest_run),
        "items": items[:limit],
        "total_issues": total_issues,
        "unclustered_count": unclustered,
        "duplicate_submissions": duplicates,
        "matched_customers": matched_customers,
        "filters": {key: value for key, value in filter_values.items() if value},
        "analysis_stale": new_since_analysis > 0,
        "new_since_analysis": new_since_analysis,
    }


@router.get("/{cluster_id}")
def get_issue(
    cluster_id: str,
    country: str | None = Query(default=None, max_length=100),
    state: str | None = Query(default=None, max_length=100),
    age_group: str | None = Query(default=None, max_length=40),
    student_status: str | None = Query(default=None, max_length=40),
    income_bracket: str | None = Query(default=None, max_length=100),
):
    with database() as connection:
        issue = connection.execute("SELECT * FROM issue_clusters WHERE cluster_id = ?", (cluster_id,)).fetchone()
        if issue is None:
            raise HTTPException(status_code=404, detail="Issue cluster not found")
        filters = {
            "country": country, "state": state, "age_group": age_group,
            "student_status": student_status, "income_bracket": income_bracket,
        }
        conditions = ["complaints.issue_cluster_id = ?"]
        values: list[object] = [cluster_id]
        for column, value in filters.items():
            if value:
                conditions.append(f"customers.{column} = ?")
                values.append(value)
        complaints = connection.execute(
            """SELECT complaints.complaint_id, complaints.customer_id, complaints.complaint_text,
                      complaints.channel, complaints.submitted_at, complaints.severity,
                      complaints.severity_source, complaints.duplicate_of
               FROM complaints LEFT JOIN customers USING (customer_id)
               WHERE """ + " AND ".join(conditions) + " ORDER BY complaints.submitted_at ASC",
            values,
        ).fetchall()
        workflow = workflow_for_label(connection, issue["label"])
    issue_data = dict(issue)
    if issue_data.get("severity_coverage", 0) <= 0:
        issue_data["average_severity"] = None
    issue_data["needs_review"] = float(issue_data.get("cohesion_score") or 0) < LOW_COHESION_REVIEW_THRESHOLD
    issue_data["workflow"] = workflow
    return {"issue": issue_data, "complaints": [dict(row) for row in complaints]}


@router.patch("/{cluster_id}/workflow")
def update_issue_workflow(cluster_id: str, update: IssueWorkflowUpdate):
    with database() as connection:
        issue = connection.execute("SELECT label FROM issue_clusters WHERE cluster_id = ?", (cluster_id,)).fetchone()
        if issue is None:
            raise HTTPException(status_code=404, detail="Issue cluster not found")
        key = issue_key(issue["label"])
        connection.execute(
            """INSERT INTO issue_work_items (issue_key, status, owner, notes, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(issue_key) DO UPDATE SET status = excluded.status,
                 owner = excluded.owner, notes = excluded.notes, updated_at = CURRENT_TIMESTAMP""",
            (key, update.status, update.owner.strip() if update.owner else None, update.notes.strip()),
        )
        workflow = workflow_for_label(connection, issue["label"])
    return workflow
