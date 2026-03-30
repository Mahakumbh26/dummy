# metrics_fetcher.py
# Fetches ALL required metrics from Prometheus HTTP API.
# Covers: requests, errors, latency, CPU, memory, FDs, GC, uptime.

import time
import requests
from datetime import datetime, timezone

try:
    from config import PROMETHEUS_URL, TIME_RANGES, STEP_RESOLUTION
except ImportError:
    from config import PROMETHEUS_URL, TIME_RANGES, STEP_RESOLUTION


# ── Prometheus helpers ────────────────────────────────────────────────────────

def _q(promql: str) -> list:
    """Instant query — returns result list or []."""
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query",
                         params={"query": promql}, timeout=12)
        r.raise_for_status()
        d = r.json()
        return d["data"]["result"] if d.get("status") == "success" else []
    except Exception:
        return []


def _qr(promql: str, start: float, end: float, step: str) -> list:
    """Range query — returns result list or []."""
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range",
                         params={"query": promql, "start": start,
                                 "end": end, "step": step}, timeout=15)
        r.raise_for_status()
        d = r.json()
        return d["data"]["result"] if d.get("status") == "success" else []
    except Exception:
        return []


def _f(val, default=0.0) -> float:
    """Safe float conversion, guards NaN."""
    try:
        v = float(val)
        return default if v != v else v
    except (TypeError, ValueError):
        return default


def _trend(result: list) -> list:
    """Extract [{ts, value}] from range query result."""
    if not result:
        return []
    return [{"ts": int(ts), "value": _f(v)}
            for ts, v in result[0].get("values", [])]


def _bounds(time_range: str):
    now = time.time()
    dur = TIME_RANGES.get(time_range)
    if not dur:
        raise ValueError(f"Invalid time_range '{time_range}'. Use: 5m, 6h, 24h.")
    step = STEP_RESOLUTION[time_range]
    return now - dur, now, step, time_range   # return time_range as prom_dur


def _lbl(instance: str, job: str) -> str:
    return f'instance="{instance}",job="{job}"'


# ── Metric fetchers ───────────────────────────────────────────────────────────

def fetch_requests(instance, job, time_range):
    start, end, step, dur = _bounds(time_range)
    lbl = _lbl(instance, job)

    # Total requests (increase over window)
    total_raw = _q(f'sum(increase(http_requests_total{{{lbl}}}[{dur}]))')
    total = _f(total_raw[0]["value"][1]) if total_raw else None

    # Requests per second (rate)
    rps_raw = _q(f'sum(rate(http_requests_total{{{lbl}}}[{dur}]))')
    rps = _f(rps_raw[0]["value"][1]) if rps_raw else None

    # Trend
    trend_raw = _qr(f'sum(rate(http_requests_total{{{lbl}}}[5m]))', start, end, step)

    return {
        "total_requests": total,
        "requests_per_sec": rps,
        "trend": _trend(trend_raw),
    }


def fetch_errors(instance, job, time_range):
    start, end, step, dur = _bounds(time_range)
    lbl = _lbl(instance, job)

    # Try http_errors_total first, fall back to http_requests_total with status filter
    err_direct = _q(f'sum(increase(http_errors_total{{{lbl}}}[{dur}]))')
    if err_direct:
        total_errors = _f(err_direct[0]["value"][1])
    else:
        e4_raw = _q(f'sum(increase(http_requests_total{{{lbl},status=~"4.."}}[{dur}]))')
        e5_raw = _q(f'sum(increase(http_requests_total{{{lbl},status=~"5.."}}[{dur}]))')
        total_errors = _f(e4_raw[0]["value"][1] if e4_raw else 0) + \
                       _f(e5_raw[0]["value"][1] if e5_raw else 0)

    total_req_raw = _q(f'sum(increase(http_requests_total{{{lbl}}}[{dur}]))')
    total_req = _f(total_req_raw[0]["value"][1]) if total_req_raw else None

    rate = round((total_errors / total_req) * 100, 3) if total_req and total_req > 0 else 0.0

    # Error rate trend
    trend_raw = _qr(
        f'sum(rate(http_requests_total{{{lbl},status=~"[45].."}}[5m])) / '
        f'sum(rate(http_requests_total{{{lbl}}}[5m])) * 100',
        start, end, step
    )

    return {
        "total_errors": total_errors,
        "total_requests": total_req,
        "error_rate_percent": rate,
        "trend": _trend(trend_raw),
    }


def fetch_latency(instance, job, time_range):
    start, end, step, dur = _bounds(time_range)
    lbl = _lbl(instance, job)

    results = {}
    for q, key in [("0.5", "p50"), ("0.95", "p95"), ("0.99", "p99")]:
        raw = _q(
            f'histogram_quantile({q},'
            f'sum(rate(http_request_duration_seconds_bucket{{{lbl}}}[{dur}])) by (le))'
        )
        results[key] = _f(raw[0]["value"][1]) if raw else None

    # Average latency via sum/count
    sum_raw   = _q(f'sum(increase(http_request_duration_seconds_sum{{{lbl}}}[{dur}]))')
    count_raw = _q(f'sum(increase(http_request_duration_seconds_count{{{lbl}}}[{dur}]))')
    s = _f(sum_raw[0]["value"][1])   if sum_raw   else None
    c = _f(count_raw[0]["value"][1]) if count_raw else None
    results["avg"] = (s / c) if s and c and c > 0 else results.get("p50")

    # p95 trend
    trend_raw = _qr(
        f'histogram_quantile(0.95,'
        f'sum(rate(http_request_duration_seconds_bucket{{{lbl}}}[5m])) by (le))',
        start, end, step
    )
    results["trend"] = _trend(trend_raw)
    return results


def fetch_cpu(instance, job, time_range):
    start, end, step, dur = _bounds(time_range)
    lbl = _lbl(instance, job)

    raw = _q(f'rate(process_cpu_seconds_total{{{lbl}}}[{dur}]) * 100')
    current = _f(raw[0]["value"][1]) if raw else None

    trend_raw = _qr(f'rate(process_cpu_seconds_total{{{lbl}}}[5m]) * 100', start, end, step)
    return {"current_percent": current, "trend": _trend(trend_raw)}


def fetch_memory(instance, job, time_range):
    start, end, step, _ = _bounds(time_range)
    lbl = _lbl(instance, job)

    rss_raw = _q(f'process_resident_memory_bytes{{{lbl}}}')
    vms_raw = _q(f'process_virtual_memory_bytes{{{lbl}}}')

    rss = _f(rss_raw[0]["value"][1]) if rss_raw else None
    vms = _f(vms_raw[0]["value"][1]) if vms_raw else None

    trend_raw = _qr(f'process_resident_memory_bytes{{{lbl}}}', start, end, step)
    # Convert trend bytes → MB
    trend_mb = [{"ts": p["ts"], "value": p["value"] / 1024**2}
                for p in _trend(trend_raw)]

    return {
        "rss_bytes": rss,
        "rss_mb":    round(rss / 1024**2, 2) if rss else None,
        "vms_mb":    round(vms / 1024**2, 2) if vms else None,
        "trend":     trend_mb,
    }


def fetch_fds(instance, job, time_range):
    lbl = _lbl(instance, job)
    open_raw = _q(f'process_open_fds{{{lbl}}}')
    max_raw  = _q(f'process_max_fds{{{lbl}}}')

    open_fds = _f(open_raw[0]["value"][1]) if open_raw else None
    max_fds  = _f(max_raw[0]["value"][1])  if max_raw  else None
    usage_pct = round((open_fds / max_fds) * 100, 1) if open_fds and max_fds else None

    return {
        "open_fds":    open_fds,
        "max_fds":     max_fds,
        "usage_percent": usage_pct,
    }


def fetch_gc(instance, job, time_range):
    _, _, _, dur = _bounds(time_range)
    lbl = _lbl(instance, job)

    col_raw = _q(f'sum(increase(python_gc_objects_collected_total{{{lbl}}}[{dur}]))')
    unc_raw = _q(f'sum(increase(python_gc_objects_uncollectable_total{{{lbl}}}[{dur}]))')

    return {
        "collected":     _f(col_raw[0]["value"][1]) if col_raw else None,
        "uncollectable": _f(unc_raw[0]["value"][1]) if unc_raw else None,
    }


def fetch_uptime(instance, job, time_range):
    lbl = _lbl(instance, job)
    raw = _q(f'app_uptime_seconds{{{lbl}}}')
    seconds = _f(raw[0]["value"][1]) if raw else None

    if seconds is None:
        return {"seconds": None, "human": "N/A"}

    days    = int(seconds // 86400)
    hours   = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)

    parts = []
    if days:    parts.append(f"{days}d")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    human = " ".join(parts) if parts else "< 1 minute"

    return {"seconds": seconds, "human": human}


# ── Master fetch ──────────────────────────────────────────────────────────────

def fetch_all(instance: str, job: str, time_range: str) -> dict:
    """Fetch all metric groups with safe error wrapping."""
    def safe(fn):
        try:
            return fn(instance, job, time_range)
        except Exception as e:
            return {"error": str(e)}

    return {
        "instance":   instance,
        "job":        job,
        "time_range": time_range,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "requests":   safe(fetch_requests),
        "errors":     safe(fetch_errors),
        "latency":    safe(fetch_latency),
        "cpu":        safe(fetch_cpu),
        "memory":     safe(fetch_memory),
        "fds":        safe(fetch_fds),
        "gc":         safe(fetch_gc),
        "uptime":     safe(fetch_uptime),
    }
