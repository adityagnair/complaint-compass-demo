from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database import DATABASE_URL, database, initialize_database
from backend.routes.analytics import router as analytics_router
from backend.routes.analysis import compatibility_router as analysis_compatibility_router
from backend.routes.analysis import router as analysis_router
from backend.routes.complaints import router as complaints_router
from backend.routes.customers import router as customers_router
from backend.routes.issues import router as issues_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Complaint Compass API", version="0.2.0", lifespan=lifespan)
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"}
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if DEMO_MODE else allowed_origins,
    allow_credentials=not DEMO_MODE,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def public_demo_read_only(request: Request, call_next):
    if DEMO_MODE and request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        return JSONResponse(status_code=403, content={"detail": "This public demo is read-only."})
    return await call_next(request)


app.include_router(complaints_router)
app.include_router(customers_router)
app.include_router(analytics_router)
app.include_router(analysis_router)
app.include_router(analysis_compatibility_router)
app.include_router(issues_router)


@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str | bool]:
    with database() as connection:
        connection.execute("SELECT 1").fetchone()
    return {
        "status": "ok",
        "service": "complaint-compass-api",
        "database": "postgresql" if DATABASE_URL else "sqlite",
        "demo_mode": DEMO_MODE,
    }
