from fastapi import APIRouter, HTTPException

from backend.models.schemas import AnalysisRequest

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
compatibility_router = APIRouter(tags=["analysis"])


@router.post("/run")
def analyze_complaints(settings: AnalysisRequest):
    # Import the ML stack only when an analysis request actually runs. The
    # read-only public demo rejects POST requests before this route is called.
    from backend.ai.embeddings import EmbeddingModelUnavailable
    from backend.ai.pipeline import run_analysis

    try:
        return run_analysis(
            min_cluster_size=settings.min_cluster_size,
            duplicate_similarity_threshold=settings.duplicate_similarity_threshold,
            duplicate_window_days=settings.duplicate_window_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbeddingModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis could not be completed: {exc}") from exc


compatibility_router.add_api_route(
    "/api/complaints/analyze", analyze_complaints, methods=["POST"], name="analyze_complaints_compat"
)
