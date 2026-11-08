from fastapi import APIRouter, HTTPException, Query

from backend.database import database
from backend.services.prioritization import score_issues

router = APIRouter(prefix="/api/issues", tags=["issues"])


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
            return {"latest_analysis": None, "items": [], "total_issues": 0, "unclustered_count": 0, "duplicate_submissions": 0}
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
                          complaints.severity, complaints.duplicate_of, complaints.issue_cluster_id,
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
            item["average_severity"] = round(sum(row["severity"] for row in primary) / len(primary), 2)
            items.append(item)
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
    return {
        "latest_analysis": dict(latest_run),
        "items": items[:limit],
        "total_issues": total_issues,
        "unclustered_count": unclustered,
        "duplicate_submissions": duplicates,
        "matched_customers": matched_customers,
        "filters": {key: value for key, value in filter_values.items() if value},
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
                      complaints.channel, complaints.submitted_at, complaints.severity, complaints.duplicate_of
               FROM complaints LEFT JOIN customers USING (customer_id)
               WHERE """ + " AND ".join(conditions) + " ORDER BY complaints.submitted_at ASC",
            values,
        ).fetchall()
    return {"issue": dict(issue), "complaints": [dict(row) for row in complaints]}
