# config.py — Central configuration for EMS backend

import os

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "https://monitoring-prometheus-production-5144.up.railway.app"
)

# Alert thresholds used across analyzer + business_insights
THRESHOLDS = {
    "latency_avg_ms":      {"fast": 200,  "slow": 1000},   # ms
    "error_rate_percent":  {"warning": 1.0, "critical": 5.0},
    "cpu_percent":         {"warning": 70.0, "critical": 90.0},
    "memory_mb":           {"healthy": 200, "moderate": 500},  # <200 healthy, 200-500 moderate, >500 high
    "gc_uncollectable":    {"warning": 10,  "critical": 50},
    "fd_usage_percent":    {"warning": 70,  "critical": 90},
}

TIME_RANGES = {
    "5m":  5  * 60,
    "6h":  6  * 3600,
    "24h": 24 * 3600,
}

STEP_RESOLUTION = {
    "5m":  "15s",
    "6h":  "1m",
    "24h": "5m",
}
