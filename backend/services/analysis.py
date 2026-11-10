import logging
from threading import Lock

logger = logging.getLogger(__name__)
_analysis_lock = Lock()


def refresh_issue_analysis() -> dict:
    from backend.ai.pipeline import run_analysis

    try:
        with _analysis_lock:
            result = run_analysis()
        return {
            "status": "completed",
            "run_id": result["run_id"],
            "issues_found": result["issues_found"],
            "complaints_processed": result["complaints_processed"],
            "duplicate_submissions": result["duplicate_submissions"],
            "unclustered_count": result["unclustered_count"],
        }
    except Exception:
        logger.exception("Automatic issue analysis failed after complaint ingestion")
        return {
            "status": "failed",
            "error": "Automatic issue analysis failed; use Analyze complaints to retry.",
        }
