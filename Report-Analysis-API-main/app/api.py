# api.py — FastAPI application
# ALL endpoints are project_name based. No manual instance/job input needed.
#
# Endpoints:
#   GET /                          → health check
#   GET /projects                  → auto-detected project list
#   GET /report?project_name=&time_range=
#   GET /download/pdf?project_name=&time_range=
#   GET /download/html?project_name=&time_range=

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware

try:
    from project_detector import detect_projects, get_project_by_id, get_project_by_name
    from metrics_fetcher import fetch_all
    from analyzer import analyze_all
    from report_generator import generate_html_report, generate_pdf_report
    from alerts import router as alerts_router
except ImportError:
    from app.project_detector import detect_projects, get_project_by_id, get_project_by_name
    from app.metrics_fetcher import fetch_all
    from app.analyzer import analyze_all
    from app.report_generator import generate_html_report, generate_pdf_report
    from app.alerts import router as alerts_router


app = FastAPI(
    title="EMS Application Health Report API",
    description=(
        "Auto-detects projects from Prometheus and generates "
        "11-section business health reports. No manual input required."
    ),
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_project(project_name: str) -> dict:
    """
    Resolve project_name → {job, instance}.
    Tries project_id match first, then display name match.
    Raises 404 if not found.
    """
    project = get_project_by_id(project_name) or get_project_by_name(project_name)
    if not project:
        # Give the caller a helpful list of valid names
        try:
            available = [p["project_id"] for p in detect_projects()]
        except Exception:
            available = []
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Project '{project_name}' not found in Prometheus.",
                "hint":  "Use GET /projects to see all available project IDs.",
                "available_project_ids": available,
            },
        )
    return project


def _build_report(project_name: str, time_range: str) -> dict:
    """Full pipeline: resolve → fetch → analyze."""
    if time_range not in ("5m", "6h", "24h"):
        raise HTTPException(
            status_code=400,
            detail="time_range must be one of: 5m, 6h, 24h",
        )
    project = _resolve_project(project_name)
    try:
        raw    = fetch_all(project["instance"], project["job"], time_range)
        report = analyze_all(raw)
        # Attach clean project metadata for display
        report["project_name"]    = project["project_name"]
        report["project_id"]      = project["project_id"]
        report["display_url"]     = project["display_url"]
        report["project_health"]  = project["health"]
        return report
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {
        "status":  "ok",
        "message": "EMS Health Report API is running.",
        "version": "4.0.0",
        "docs":    "/docs",
    }


@app.get("/projects", tags=["Projects"],
         summary="Auto-detect all projects from Prometheus")
def list_projects():
    """
    Automatically fetches all active Prometheus targets and returns
    a clean project list. Frontend uses this to build the project selector.

    Response:
    {
      "total": 15,
      "projects": [
        {
          "project_name": "EMS Backend",
          "project_id":   "ems_backend",       ← use this in /report calls
          "job":          "EMS_Backend",
          "instance":     "employeemgmt.railway.app",
          "health":       "up",
          "display_url":  "employeemgmt.railway.app"
        },
        ...
      ]
    }
    """
    try:
        projects = detect_projects()
        return {"total": len(projects), "projects": projects}
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/report", tags=["Reports"],
         summary="Generate full 11-section health report by project name")
def get_report(
    project_name: str = Query(
        ...,
        description="Use project_id from GET /projects (e.g. 'ems_backend')",
        example="ems_backend",
    ),
    time_range: str = Query(
        "6h",
        description="Time window: 5m | 6h | 24h",
    ),
):
    """
    Returns a complete 11-section business health report.
    No instance or job needed — just pass the project_id from /projects.

    Sections:
      1. Project Details       2. Executive Summary    3. Key Metrics
      4. Performance Analysis  5. Error Analysis       6. Resource Usage
      7. Memory & GC           8. System Stability     9. Business Impact
      10. Recommended Actions  11. Final Status

    Example:
        GET /report?project_name=ems_backend&time_range=6h
        GET /report?project_name=climateeye_api&time_range=24h
    """
    report = _build_report(project_name, time_range)
    report.pop("_raw", None)
    return JSONResponse(content=report)


@app.get("/download/pdf", tags=["Downloads"],
         summary="Download PDF health report by project name")
def download_pdf(
    project_name: str = Query(..., example="ems_backend"),
    time_range:   str = Query("6h"),
):
    """
    Generates and streams a PDF report with all 11 sections + trend charts.

    Frontend button:
        <a href="/download/pdf?project_name=ems_backend&time_range=24h" download>
          Download PDF
        </a>

    Or JavaScript:
        const url = `/download/pdf?project_name=${projectId}&time_range=${range}`;
        window.open(url);
    """
    report    = _build_report(project_name, time_range)
    pdf_bytes = generate_pdf_report(report)
    fname     = f"health_report_{project_name}_{time_range}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/download/html", tags=["Downloads"],
         summary="Download HTML health report by project name")
def download_html(
    project_name: str = Query(..., example="ems_backend"),
    time_range:   str = Query("6h"),
):
    report = _build_report(project_name, time_range)
    html   = generate_html_report(report)
    fname  = f"health_report_{project_name}_{time_range}.html"
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
