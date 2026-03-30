# project_detector.py
# Auto-detects all projects from Prometheus.
# No manual input needed — everything is derived from labels.
# Frontend only needs to pass project_name.

import re
import requests

try:
    from config import PROMETHEUS_URL
except ImportError:
    from config import PROMETHEUS_URL


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_name(job: str, instance: str) -> str:
    """
    Derive a clean, readable project name from job label.
    Examples:
        "EMS_Backend"  → "EMS Backend"
        "Climateeye_api" → "Climateeye Api"
        "admin_crop_api" → "Admin Crop Api"
    """
    name = job.strip()
    # Replace underscores/hyphens with spaces
    name = re.sub(r"[_\-]+", " ", name)
    # Title-case each word
    name = name.title()
    return name


def _project_id(job: str, instance: str) -> str:
    """Stable slug used as the project_name key in API calls."""
    # Lowercase, replace spaces/special chars with underscore
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", job).strip("_").lower()
    return slug


# ── Core detection ────────────────────────────────────────────────────────────

def detect_projects() -> list[dict]:
    """
    Fetch all active Prometheus targets and return a clean project list.
    Each project = unique (job + instance) combination.

    Returns list of:
    {
        "project_name":   "EMS Backend",          ← human-readable display name
        "project_id":     "ems_backend",           ← used in API calls
        "job":            "EMS_Backend",           ← raw Prometheus job label
        "instance":       "employeemgmt.railway.app",
        "health":         "up" | "down" | "unknown",
        "last_scrape":    "2026-03-27T...",
        "display_url":    "employeemgmt.railway.app"  ← cleaned instance for display
    }
    """
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/targets",
            timeout=12,
        )
        r.raise_for_status()
        targets = r.json().get("data", {}).get("activeTargets", [])
    except Exception as e:
        raise RuntimeError(f"Cannot reach Prometheus: {e}")

    seen_ids = {}   # project_id → index, to handle duplicates
    projects = []

    for t in targets:
        job      = t["labels"].get("job", "").strip()
        instance = t["labels"].get("instance", "").strip()

        if not job or not instance:
            continue

        pid          = _project_id(job, instance)
        display_name = _clean_name(job, instance)

        # If same job slug appears multiple times (multiple instances),
        # append a short suffix to keep IDs unique
        if pid in seen_ids:
            # Use last segment of instance as differentiator
            suffix = instance.split(".")[0].lower()
            suffix = re.sub(r"[^a-z0-9]", "", suffix)[:8]
            pid = f"{pid}_{suffix}"

        seen_ids[pid] = True

        # Clean instance for display (strip https://, trailing slashes)
        display_url = re.sub(r"^https?://", "", instance).rstrip("/")

        projects.append({
            "project_name": display_name,
            "project_id":   pid,
            "job":          job,
            "instance":     instance,
            "health":       t.get("health", "unknown"),
            "last_scrape":  t.get("lastScrape", ""),
            "display_url":  display_url,
        })

    # Sort: healthy first, then alphabetically by name
    projects.sort(key=lambda p: (0 if p["health"] == "up" else 1, p["project_name"]))
    return projects


def get_project_by_id(project_id: str) -> dict | None:
    """
    Look up a project by its project_id.
    Returns the project dict or None if not found.
    """
    projects = detect_projects()
    for p in projects:
        if p["project_id"] == project_id:
            return p
    return None


def get_project_by_name(project_name: str) -> dict | None:
    """
    Look up a project by display name (case-insensitive).
    Falls back to project_id match as well.
    """
    projects = detect_projects()
    name_lower = project_name.strip().lower()
    for p in projects:
        if (p["project_name"].lower() == name_lower or
                p["project_id"].lower() == name_lower):
            return p
    return None
