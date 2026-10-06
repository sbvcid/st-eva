"""
FastAPI application for ST-EVA Web API and static frontend serving.
Strictly decoupled HTTP/JSON interface to ST-EVA background analysis.
"""

from pathlib import Path
import re
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.job_manager import JobManager
from web.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthResponse,
    JobDetailResponse,
)

# Valid ticker characters: letters, digits, '.', '-', ':' (e.g. 0700.HK, BRK.B, TSLA)
TICKER_PATTERN = re.compile(r"^[A-Za-z0-9\.\:\-_]{1,16}$")


def validate_ticker(ticker: str) -> str:
    cleaned = ticker.strip()
    if not cleaned or not TICKER_PATTERN.match(cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ticker format: '{ticker}'. Ticker must be 1-16 alphanumeric characters (dots/hyphens allowed).",
        )
    return cleaned.upper()


def create_app(
    job_manager: Optional[JobManager] = None,
    frontend_dist: Optional[str] = None,
) -> FastAPI:
    app = FastAPI(
        title="ST-EVA Web API",
        description="HTTP/JSON REST API for ST-EVA reverse valuation engine.",
        version="0.1.0",
    )

    # Configurable CORS policy allowing modern browser & mobile clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    manager = job_manager or JobManager()
    app.state.job_manager = manager

    @app.get("/api/health", response_model=HealthResponse)
    def health_check() -> HealthResponse:
        return HealthResponse(status="ok", version="0.1.0")

    @app.post("/api/analyze", response_model=AnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
    def start_analysis(request: AnalyzeRequest) -> AnalyzeResponse:
        valid_ticker = validate_ticker(request.ticker)
        record = manager.submit_job(
            ticker=valid_ticker,
            mode=request.mode,
            reference_multiple=request.reference_multiple,
            horizon_years=request.horizon_years,
        )
        return AnalyzeResponse(
            job_id=record.job_id,
            ticker=record.ticker,
            status=record.status,
        )

    @app.get("/api/jobs/{job_id}", response_model=JobDetailResponse)
    def get_job_status(job_id: str) -> JobDetailResponse:
        record = manager.get_job(job_id)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        return record.to_response()

    # Mount static assets if frontend dist directory exists
    dist_path = Path(frontend_dist) if frontend_dist else Path(__file__).resolve().parent / "frontend" / "dist"
    if dist_path.exists():
        assets_dir = dist_path / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            # If requesting an existing static file (e.g. favicon, manifest, sw.js, icons)
            candidate = dist_path / full_path
            if full_path and candidate.exists() and candidate.is_file():
                if candidate.name == "sw.js":
                    return FileResponse(
                        candidate,
                        media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
                    )
                if candidate.suffix == ".webmanifest":
                    return FileResponse(candidate, media_type="application/manifest+json")
                return FileResponse(candidate)
            # Default to index.html for SPA client-side routing
            index_html = dist_path / "index.html"
            if index_html.exists():
                return FileResponse(index_html)
            raise HTTPException(status_code=404, detail="Frontend dist not found")

    return app


app = create_app()


def main() -> None:
    """Entry point for python -m web.api.app or python -m web.app."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="ST-EVA Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--reload", action="store_true", help="Enable reload for development")
    args = parser.parse_args()

    print(f"Starting ST-EVA Web Server on http://{args.host}:{args.port}")
    uvicorn.run("web.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
