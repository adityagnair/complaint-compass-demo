from fastapi import APIRouter, HTTPException, Query

from backend.database import database

router = APIRouter(prefix="/api/issues", tags=["issues"])


@router.get("/top10")
@router.get("")
def list_issues(limit: int = Query(default=10, ge=1, le=200)):
    with database() as connection:
        latest_run = connection.execute(
            "SELECT * FROM analysis_runs ORDER BY created_at DESC, run_id DESC LIMIT 1"
        ).fetchone()
        if latest_run is None:
            return {"latest_analysis": None, "items": [], "total_issues": 0, "unclustered_count": 0, "duplicate_submissions": 0}
        total_issues = connection.execute(
            "SELECT COUNT(*) FROM issue_clusters WHERE run_id = ?", (latest_run["run_id"],)
        ).fetchone()[0]
        items = connection.execute(
            """SELECT * FROM issue_clusters WHERE run_id = ?
               ORDER BY priority_score DESC, affected_customers DESC, complaint_count DESC LIMIT ?""",
            (latest_run["run_id"], limit),
        ).fetchall()
        unclustered = connection.execute(
            "SELECT COUNT(*) FROM complaints WHERE issue_cluster_id IS NULL AND duplicate_of IS NULL"
        ).fetchone()[0]
        duplicates = connection.execute("SELECT COUNT(*) FROM complaints WHERE duplicate_of IS NOT NULL").fetchone()[0]
    return {
        "latest_analysis": dict(latest_run),
        "items": [dict(item) for item in items],
        "total_issues": total_issues,
        "unclustered_count": unclustered,
        "duplicate_submissions": duplicates,
    }


@router.get("/{cluster_id}")
def get_issue(cluster_id: str):
    with database() as connection:
        issue = connection.execute("SELECT * FROM issue_clusters WHERE cluster_id = ?", (cluster_id,)).fetchone()
        if issue is None:
            raise HTTPException(status_code=404, detail="Issue cluster not found")
        complaints = connection.execute(
            """SELECT complaint_id, customer_id, complaint_text, channel, submitted_at, severity, duplicate_of
               FROM complaints WHERE issue_cluster_id = ? ORDER BY submitted_at ASC""",
            (cluster_id,),
        ).fetchall()
    return {"issue": dict(issue), "complaints": [dict(row) for row in complaints]}
