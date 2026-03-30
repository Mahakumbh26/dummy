# alerts.py — Alertmanager webhook receiver + frontend fetch
#
# Endpoints added to existing FastAPI app:
#   POST /api/alerts   ← Alertmanager webhook
#   GET  /api/alerts   ← Frontend fetches stored alerts

import os
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

# ── DB connection (lazy, singleton) ──────────────────────────────────────────

_conn = None

def _get_conn():
    global _conn
    if not PSYCOPG2_AVAILABLE:
        raise HTTPException(status_code=500, detail="psycopg2 not installed. Add psycopg2-binary to requirements.txt")

    if _conn is None or _conn.closed:
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            _conn = psycopg2.connect(db_url)
        else:
            _conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                dbname=os.getenv("DB_NAME", "alerts_db"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", ""),
                port=int(os.getenv("DB_PORT", 5432)),
            )
        _conn.autocommit = True
        _ensure_table(_conn)

    return _conn


def _ensure_table(conn):
    """Create alerts table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email (
                id          SERIAL PRIMARY KEY,
                alertname   VARCHAR(255),
                severity    VARCHAR(50),
                project     VARCHAR(255),
                instance    VARCHAR(255),
                status      VARCHAR(50),
                description TEXT,
                email_to    VARCHAR(255),
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)


# ── POST /api/alerts — Alertmanager webhook ───────────────────────────────────

@router.post("", summary="Alertmanager webhook receiver")
async def receive_alerts(request: Request):
    """
    Receives alerts from Alertmanager and stores them in PostgreSQL.

    Alertmanager config:
        webhook_configs:
          - url: "https://your-api.up.railway.app/api/alerts"
            send_resolved: true
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    alerts = data.get("alerts", [])
    if not alerts:
        return JSONResponse({"message": "No alerts in payload", "count": 0})

    conn = _get_conn()
    stored = 0

    with conn.cursor() as cur:
        for alert in alerts:
            labels      = alert.get("labels", {})
            annotations = alert.get("annotations", {})

            cur.execute(
                """
                INSERT INTO email (alertname, severity, project, instance, status, description, email_to)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    labels.get("alertname"),
                    labels.get("severity"),
                    labels.get("job"),
                    labels.get("instance"),
                    alert.get("status"),
                    annotations.get("description"),
                    alert.get("to"),
                ),
            )
            stored += 1

    logger.info("Stored %d alert(s) from Alertmanager", stored)
    return JSONResponse({"message": "Alerts received", "count": stored}, status_code=200)


# ── GET /api/alerts — Frontend fetch ─────────────────────────────────────────

@router.get("", summary="Fetch all stored alerts for frontend")
def get_alerts(
    limit: int = 100,
    status: str = None,
    severity: str = None,
):
    """
    Returns stored alerts ordered by newest first.

    Query params (all optional):
      - limit:    max results (default 100)
      - status:   filter by status (firing | resolved)
      - severity: filter by severity (critical | warning | info)

    Example:
        GET /api/alerts
        GET /api/alerts?status=firing&severity=critical
        GET /api/alerts?limit=50
    """
    conn = _get_conn()

    query  = "SELECT id, alertname, severity, project, instance, status, description, email_to, created_at FROM email"
    params = []
    where  = []

    if status:
        where.append("status = %s")
        params.append(status)
    if severity:
        where.append("severity = %s")
        params.append(severity)

    if where:
        query += " WHERE " + " AND ".join(where)

    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    result = []
    for row in rows:
        result.append({
            "id":          row["id"],
            "alertname":   row["alertname"],
            "severity":    row["severity"],
            "project":     row["project"],
            "instance":    row["instance"],
            "status":      row["status"],
            "description": row["description"],
            "email_to":    row["email_to"],
            "time":        row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row["created_at"] else None,
        })

    return JSONResponse(result)
