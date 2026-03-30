# analyzer.py — Converts raw metrics into the 11-section report.
# Same structure as before. Improved content:
#   - Missing data is flagged as a monitoring gap, not silently ignored
#   - Every section has richer plain-English explanations
#   - Actions are ALWAYS generated (even for healthy systems)
#   - Tool recommendations embedded inside relevant sections
#   - Final status includes a clear justification sentence

try:
    from config import THRESHOLDS
except ImportError:
    from config import THRESHOLDS


def _f(v, default=0.0):
    if v is None:
        return default
    try:
        x = float(v)
        return default if x != x else x
    except (TypeError, ValueError):
        return default


def _trend_dir(trend: list) -> str:
    if not trend or len(trend) < 5:
        return "Stable"
    n = len(trend)
    seg = max(1, n // 5)
    early = sum(p["value"] for p in trend[:seg]) / seg
    late  = sum(p["value"] for p in trend[-seg:]) / seg
    pct   = ((late - early) / (early + 1e-9)) * 100
    if pct > 10:  return "Increasing"
    if pct < -10: return "Decreasing"
    return "Stable"


def _missing(field_name: str) -> str:
    """Standard message for missing metric data."""
    return (
        f"⚠️ Data not available — {field_name} metric is not being collected. "
        "This is a monitoring gap. Add the required Prometheus exporter or instrumentation "
        "to enable this metric. Without it, decisions about this area cannot be made accurately."
    )


# ── Section 3: Key Metrics ────────────────────────────────────────────────────

def build_key_metrics(raw: dict) -> dict:
    req = raw.get("requests", {})
    err = raw.get("errors",   {})
    lat = raw.get("latency",  {})
    cpu = raw.get("cpu",      {})
    mem = raw.get("memory",   {})
    upt = raw.get("uptime",   {})

    avg_s  = lat.get("avg") or lat.get("p50")
    avg_ms = round(_f(avg_s) * 1000, 1) if avg_s is not None else None

    total_req = req.get("total_requests")
    total_err = _f(err.get("total_errors", 0))
    err_rate  = _f(err.get("error_rate_percent", 0.0))
    cpu_pct   = cpu.get("current_percent")
    rss_mb    = mem.get("rss_mb")

    # Data quality flags — track which metrics are missing
    missing = []
    if avg_ms is None:       missing.append("response_time")
    if total_req is None:    missing.append("request_count")
    if cpu_pct is None:      missing.append("cpu_usage")
    if rss_mb is None:       missing.append("memory_usage")
    if upt.get("seconds") is None: missing.append("uptime")

    return {
        "total_requests":  round(_f(total_req)) if total_req is not None else "N/A — monitoring gap",
        "total_errors":    round(total_err),
        "error_rate_pct":  round(err_rate, 2),
        "avg_response_ms": avg_ms,
        "cpu_percent":     round(_f(cpu_pct), 2) if cpu_pct is not None else None,
        "memory_mb":       rss_mb,
        "uptime":          upt.get("human", "N/A — monitoring gap"),
        "uptime_seconds":  upt.get("seconds"),
        "missing_metrics": missing,
    }


# ── Section 4: Performance ────────────────────────────────────────────────────

def build_performance(raw: dict) -> dict:
    lat   = raw.get("latency", {})
    avg_s = lat.get("avg") or lat.get("p50")
    p95_s = lat.get("p95")
    p99_s = lat.get("p99")

    avg_ms = round(_f(avg_s) * 1000, 1) if avg_s is not None else None
    p95_ms = round(_f(p95_s) * 1000, 1) if p95_s is not None else None
    p99_ms = round(_f(p99_s) * 1000, 1) if p99_s is not None else None
    trend  = _trend_dir(lat.get("trend", []))

    t = THRESHOLDS["latency_avg_ms"]

    if avg_ms is None:
        return {
            "avg_ms": None, "p95_ms": None, "p99_ms": None,
            "classification": "Unknown", "label": "❓",
            "trend": trend,
            "explanation": (
                "⚠️ Response time data is missing — user experience cannot be evaluated. "
                "This is a critical monitoring gap. Without latency data, we cannot tell "
                "whether users are experiencing fast or slow responses. "
                "Instrument your application with http_request_duration_seconds histogram "
                "and use Grafana to visualize response time trends."
            ),
            "data_quality": "missing",
        }

    if avg_ms < t["fast"]:
        classification, label = "Fast", "✅"
        explanation = (
            f"The API is responding quickly — average response time is {avg_ms} ms. "
            f"95% of all requests complete within {p95_ms} ms. "
            "Users are getting fast, smooth responses. This is the ideal state. "
            "Use Grafana dashboards to continue monitoring latency trends over time."
        )
    elif avg_ms < t["slow"]:
        classification, label = "Moderate", "⚠️"
        explanation = (
            f"API response time is moderate at {avg_ms} ms on average. "
            f"95% of requests complete within {p95_ms} ms. "
            "Most users will not notice, but during peak traffic hours this could worsen. "
            "Consider reviewing slow database queries or adding a caching layer (e.g., Redis). "
            "Use Grafana to identify which endpoints are slowest."
        )
    else:
        classification, label = "Slow", "🔴"
        explanation = (
            f"The API is responding slowly — average response time is {avg_ms} ms. "
            f"95% of requests take up to {p95_ms} ms. "
            "Users are experiencing noticeable delays. This directly affects satisfaction and retention. "
            "Immediate investigation is needed: check database queries, third-party API calls, "
            "and server resource usage. Consider scaling up or adding a CDN."
        )

    return {
        "avg_ms": avg_ms, "p95_ms": p95_ms, "p99_ms": p99_ms,
        "classification": classification, "label": label,
        "trend": trend, "explanation": explanation,
        "data_quality": "available",
    }


# ── Section 5: Error Analysis ─────────────────────────────────────────────────

def build_error_analysis(raw: dict) -> dict:
    err       = raw.get("errors", {})
    total_err = _f(err.get("total_errors", 0))
    total_req = _f(err.get("total_requests") or 0)
    rate      = _f(err.get("error_rate_percent", 0.0))
    trend     = _trend_dir(err.get("trend", []))
    t         = THRESHOLDS["error_rate_percent"]

    if total_req == 0 and total_err == 0:
        return {
            "total_errors": 0, "total_requests": "N/A — monitoring gap",
            "error_rate_pct": 0.0, "label": "❓", "status": "No Data",
            "trend": trend,
            "impact": (
                "⚠️ Request count data is not available — this is a monitoring gap. "
                "We cannot confirm whether users are experiencing errors or not. "
                "Add http_requests_total metric instrumentation to your application. "
                "Use Sentry for real-time error tracking and Alertmanager to get notified "
                "when error rates exceed acceptable thresholds."
            ),
            "data_quality": "missing",
        }

    if rate >= t["critical"]:
        label, status = "🔴", "Critical"
        impact = (
            f"{rate:.2f}% of all user requests are failing — that is roughly "
            f"{round(total_err)} errors out of {round(total_req)} total requests. "
            "Users are experiencing broken pages, failed form submissions, or lost transactions. "
            "This is directly hurting the business. Immediate action is required. "
            "Check application logs, review recent deployments, and consider a rollback. "
            "Use Sentry for detailed error tracking."
        )
    elif rate >= t["warning"]:
        label, status = "⚠️", "Warning"
        impact = (
            f"{rate:.2f}% of requests are returning errors ({round(total_err)} errors). "
            "Some users are hitting failures. Left unaddressed, this can escalate. "
            "Review error logs and identify the root cause. "
            "Set up Alertmanager rules to notify the team when error rate exceeds 1%."
        )
    else:
        label, status = "✅", "Healthy"
        impact = (
            f"No significant user-facing failures detected. "
            f"Only {round(total_err)} errors out of {round(total_req)} total requests "
            f"({rate:.2f}% error rate). "
            "Users are successfully completing their actions. The system is reliable. "
            "Continue monitoring with Grafana and maintain Alertmanager rules as a safety net."
        )

    return {
        "total_errors": round(total_err),
        "total_requests": round(total_req),
        "error_rate_pct": round(rate, 2),
        "label": label, "status": status,
        "trend": trend, "impact": impact,
        "data_quality": "available",
    }


# ── Section 6: Resource Usage ─────────────────────────────────────────────────

def build_resource_analysis(raw: dict) -> dict:
    cpu = raw.get("cpu",    {})
    mem = raw.get("memory", {})

    cpu_pct   = cpu.get("current_percent")
    rss_mb    = mem.get("rss_mb")
    cpu_trend = _trend_dir(cpu.get("trend", []))
    mem_trend = _trend_dir(mem.get("trend", []))
    t_mem     = THRESHOLDS["memory_mb"]
    t_cpu     = THRESHOLDS["cpu_percent"]

    # Memory
    if rss_mb is None:
        mem_cat, mem_label = "Unknown", "❓"
        mem_note = _missing("process_resident_memory_bytes")
    elif rss_mb < t_mem["healthy"]:
        mem_cat, mem_label = "Low", "✅"
        mem_note = (
            f"Memory usage is low at {rss_mb:.1f} MB (under 200 MB threshold). "
            "The application has plenty of memory headroom. "
            "System has enough capacity to handle increased traffic without memory pressure."
        )
    elif rss_mb < t_mem["moderate"]:
        mem_cat, mem_label = "Moderate", "⚠️"
        mem_note = (
            f"Memory usage is moderate at {rss_mb:.1f} MB (200–500 MB range). "
            "This is acceptable but worth watching. "
            "If memory continues to grow, it may indicate a memory leak. "
            "Set up Alertmanager to alert when memory exceeds 400 MB. "
            "Use Grafana to track the memory trend over time."
        )
    else:
        mem_cat, mem_label = "High", "🔴"
        mem_note = (
            f"Memory usage is high at {rss_mb:.1f} MB (above 500 MB). "
            "The application is consuming a large amount of server memory. "
            "Risk of slowdown or crash if memory continues to grow. "
            "Investigate for memory leaks immediately. Consider restarting the service "
            "as an emergency measure and scaling up server memory."
        )

    # CPU
    if cpu_pct is None:
        cpu_cat, cpu_label = "Unknown", "❓"
        cpu_note = _missing("process_cpu_seconds_total")
    elif cpu_pct >= t_cpu["critical"]:
        cpu_cat, cpu_label = "High", "🔴"
        cpu_note = (
            f"CPU usage is critically high at {cpu_pct:.1f}%. "
            "The server is overloaded and may start rejecting or delaying requests. "
            "Scale up server resources immediately. "
            "Engineering should profile the application to find CPU-intensive operations."
        )
    elif cpu_pct >= t_cpu["warning"]:
        cpu_cat, cpu_label = "Moderate", "⚠️"
        cpu_note = (
            f"CPU usage is elevated at {cpu_pct:.1f}%. "
            "The server is under significant load. "
            "Performance may degrade during traffic spikes. "
            "Plan for capacity increase and review background jobs. "
            "Use Grafana to monitor CPU trends and set Alertmanager thresholds."
        )
    else:
        cpu_cat, cpu_label = "Low", "✅"
        cpu_note = (
            f"CPU usage is low at {cpu_pct:.1f}%. "
            "The server has plenty of processing capacity. "
            "System can comfortably handle current traffic and moderate growth."
        )

    return {
        "memory_mb": rss_mb, "memory_cat": mem_cat,
        "memory_label": mem_label, "memory_note": mem_note, "memory_trend": mem_trend,
        "cpu_percent": round(_f(cpu_pct), 2) if cpu_pct is not None else None,
        "cpu_cat": cpu_cat, "cpu_label": cpu_label,
        "cpu_note": cpu_note, "cpu_trend": cpu_trend,
    }


# ── Section 7: GC Analysis ────────────────────────────────────────────────────

def build_gc_analysis(raw: dict) -> dict:
    gc        = raw.get("gc",     {})
    mem       = raw.get("memory", {})
    collected = gc.get("collected")
    unc       = gc.get("uncollectable")
    mem_trend = _trend_dir(mem.get("trend", []))
    t         = THRESHOLDS["gc_uncollectable"]
    unc_val   = _f(unc)

    if collected is None and unc is None:
        return {
            "collected": "N/A", "uncollectable": "N/A",
            "label": "❓", "status": "No Data",
            "explanation": _missing("python_gc_objects_collected_total / uncollectable_total"),
            "leak_risk": "Unknown — data not available",
            "memory_trend": mem_trend,
            "data_quality": "missing",
        }

    if unc_val >= t["critical"]:
        label, status = "🔴", "Critical"
        explanation = (
            f"{unc_val:.0f} objects could not be freed by Python's memory manager. "
            "This strongly indicates a memory leak — the application is holding onto memory "
            "it no longer needs. Over time, this will consume all available memory and crash the service. "
            "Engineering must investigate circular references in the codebase immediately."
        )
        leak_risk = "High — memory leak very likely"
    elif unc_val >= t["warning"]:
        label, status = "⚠️", "Warning"
        explanation = (
            f"{unc_val:.0f} objects could not be freed. "
            "Minor memory inefficiency detected. Low immediate risk, but worth investigating. "
            "Engineering should review recent code changes for potential memory issues."
        )
        leak_risk = "Low — monitor closely"
    else:
        col_str = f"{_f(collected):.0f}" if collected is not None else "N/A"
        label, status = "✅", "Healthy"
        explanation = (
            f"Python's memory manager is working correctly. "
            f"{col_str} objects were cleaned up successfully during this period. "
            f"Only {unc_val:.0f} objects could not be freed (within acceptable range). "
            "No memory leak detected. The system is cleaning up memory properly."
        )
        leak_risk = "None detected"

    if mem_trend == "Increasing" and status in ("Warning", "Critical"):
        leak_risk = "High — memory is growing steadily, leak pattern confirmed"

    return {
        "collected": round(_f(collected)) if collected is not None else "N/A",
        "uncollectable": round(unc_val),
        "label": label, "status": status,
        "explanation": explanation, "leak_risk": leak_risk,
        "memory_trend": mem_trend, "data_quality": "available",
    }


# ── Section 8: Stability ──────────────────────────────────────────────────────

def build_stability(raw: dict) -> dict:
    upt        = raw.get("uptime", {})
    fds        = raw.get("fds",    {})
    uptime_sec = upt.get("seconds")
    uptime_str = upt.get("human", "N/A")
    open_fds   = fds.get("open_fds")
    max_fds    = fds.get("max_fds")
    fd_pct     = fds.get("usage_percent")
    t_fd       = THRESHOLDS["fd_usage_percent"]

    # Uptime
    if uptime_sec is None:
        uptime_label = "❓"
        uptime_note  = (
            "⚠️ Uptime data is not available — this is a monitoring gap. "
            "Without uptime data, we cannot confirm how long the application has been running "
            "or whether it has crashed and restarted recently. "
            "Add the app_uptime_seconds metric to your application. "
            "Use Grafana to track uptime history and Alertmanager to alert on restarts."
        )
    elif uptime_sec < 300:
        uptime_label = "⚠️"
        uptime_note  = (
            f"Application restarted very recently (uptime: {uptime_str}). "
            "This may indicate a crash or forced restart. "
            "Check application logs to confirm whether this was planned or unexpected. "
            "Unexpected restarts mean users experienced a brief outage."
        )
    elif uptime_sec < 3600:
        uptime_label = "⚠️"
        uptime_note  = (
            f"Application has been running for {uptime_str} — recently started. "
            "Monitor closely over the next few hours to confirm stability."
        )
    else:
        uptime_label = "✅"
        uptime_note  = (
            f"Application has been running continuously for {uptime_str}. "
            "This indicates good stability — no unexpected restarts detected. "
            "Users have had uninterrupted access to the service."
        )

    # File Descriptors
    if fd_pct is None:
        fd_label = "❓"
        fd_note  = (
            "⚠️ File descriptor data is not available. "
            "File descriptors represent open connections, files, and sockets. "
            "Without this data, we cannot detect connection leaks. "
            "Ensure process_open_fds and process_max_fds metrics are being exported."
        )
    elif fd_pct >= t_fd["critical"]:
        fd_label = "🔴"
        fd_note  = (
            f"File descriptor usage is critically high at {fd_pct:.0f}% "
            f"({int(_f(open_fds))} open out of {int(_f(max_fds))} max). "
            "The application is close to running out of file descriptors. "
            "This will cause it to fail when trying to open new connections or files. "
            "Investigate for connection leaks and increase OS file descriptor limits."
        )
    elif fd_pct >= t_fd["warning"]:
        fd_label = "⚠️"
        fd_note  = (
            f"File descriptor usage is elevated at {fd_pct:.0f}% "
            f"({int(_f(open_fds))} open out of {int(_f(max_fds))} max). "
            "Monitor for further increase. Set Alertmanager alerts at 80% threshold."
        )
    else:
        fd_label = "✅"
        fd_note  = (
            f"File descriptor usage is normal — "
            f"{int(_f(open_fds))} open connections out of {int(_f(max_fds))} maximum allowed. "
            "The application is managing its connections and file handles properly."
        )

    return {
        "uptime": uptime_str, "uptime_label": uptime_label, "uptime_note": uptime_note,
        "open_fds": int(_f(open_fds)) if open_fds is not None else "N/A",
        "max_fds":  int(_f(max_fds))  if max_fds  is not None else "N/A",
        "fd_pct": fd_pct, "fd_label": fd_label, "fd_note": fd_note,
    }


# ── Section 9: Business Impact ────────────────────────────────────────────────

def build_business_impact(perf, err_a, res, gc_a, stab, km) -> list:
    impacts = []
    missing = km.get("missing_metrics", [])

    # Missing data impact — always specific, never generic
    if missing:
        impacts.append(
            f"📊 Monitoring gaps detected ({', '.join(missing)}). "
            "Business decisions based on this report may be inaccurate or incomplete. "
            "Investing in proper monitoring (Prometheus + Grafana) will give the team "
            "full visibility and prevent surprises."
        )

    if perf.get("classification") == "Slow":
        impacts.append(
            f"🐢 API is slow ({perf.get('avg_ms')} ms average). "
            "Research shows that 53% of users abandon a page that takes more than 3 seconds to load. "
            "Slow responses lead to higher bounce rates, lower conversion, and lost revenue."
        )
    elif perf.get("classification") == "Moderate":
        impacts.append(
            f"⏱ API response time is moderate ({perf.get('avg_ms')} ms). "
            "During peak hours or traffic spikes, users may notice delays. "
            "Proactive optimization now prevents a bigger problem later."
        )
    elif perf.get("classification") == "Unknown":
        impacts.append(
            "❓ API performance is unknown due to missing latency data. "
            "We cannot assess whether users are having a good or bad experience. "
            "This is a business risk — add response time monitoring immediately."
        )

    if err_a.get("status") == "Critical":
        impacts.append(
            f"❌ {err_a.get('error_rate_pct')}% error rate means users are hitting failures. "
            "Failed transactions, broken features, and error pages directly reduce revenue "
            "and damage user trust. Every minute this continues costs the business."
        )
    elif err_a.get("status") == "Warning":
        impacts.append(
            f"⚠️ {err_a.get('error_rate_pct')}% of requests are failing. "
            "A small percentage of users are experiencing errors. "
            "If left unaddressed, this can escalate and affect more users."
        )
    elif err_a.get("status") == "No Data":
        impacts.append(
            "❓ Error data is not available. "
            "We cannot confirm whether users are experiencing failures. "
            "This is a monitoring gap that must be fixed to ensure service quality."
        )

    if res.get("memory_cat") == "High":
        impacts.append(
            f"💾 High memory usage ({res.get('memory_mb'):.0f} MB) puts the system at risk of crashing. "
            "An out-of-memory crash would make the application completely unavailable to all users, "
            "resulting in downtime and potential data loss."
        )
    elif res.get("memory_cat") == "Moderate":
        impacts.append(
            f"💾 Memory usage is moderate ({res.get('memory_mb'):.0f} MB). "
            "Under increased load, memory may grow further. "
            "Proactive monitoring now prevents a future outage."
        )

    if res.get("cpu_cat") in ("High", "Moderate"):
        impacts.append(
            f"⚙️ Server CPU is under {res.get('cpu_cat', '').lower()} load ({res.get('cpu_percent')}%). "
            "During traffic spikes, the system may slow down or become unresponsive, "
            "affecting all users simultaneously."
        )

    if gc_a.get("leak_risk") not in ("None detected", "Unknown — data not available"):
        impacts.append(
            "🔍 Memory leak risk detected. "
            "Over time, the application will consume more and more memory without releasing it. "
            "This leads to gradual performance degradation and eventually a crash — "
            "often at the worst possible time (peak traffic)."
        )

    if stab.get("uptime_label") == "⚠️":
        impacts.append(
            "🔄 Recent application restart detected. "
            "Users may have experienced a brief outage or service interruption. "
            "Frequent restarts indicate instability that needs investigation."
        )

    if not impacts:
        impacts.append(
            "✅ No significant business impact detected at this time. "
            "The system is operating normally, users are having a good experience, "
            "and all key metrics are within healthy ranges. "
            "Continue routine monitoring with Grafana to maintain this status."
        )

    return impacts


# ── Section 10: Recommended Actions ──────────────────────────────────────────

def build_actions(perf, err_a, res, gc_a, stab, km) -> list:
    actions = []
    missing = km.get("missing_metrics", [])

    # Missing metrics — always highest priority to fix
    if "response_time" in missing:
        actions.append({
            "problem": "Response time (latency) metrics are not being collected",
            "impact":  "Cannot evaluate user experience or detect slow APIs",
            "action":  "Instrument your app with http_request_duration_seconds histogram. "
                       "Use Grafana to visualize and Alertmanager to alert on p95 > 1s.",
            "priority": "High",
        })
    if "request_count" in missing:
        actions.append({
            "problem": "Request count metrics are not available",
            "impact":  "Cannot calculate error rates or traffic patterns",
            "action":  "Add http_requests_total counter to your application. "
                       "Use Prometheus client library for your language.",
            "priority": "High",
        })
    if "uptime" in missing:
        actions.append({
            "problem": "Application uptime metric is missing",
            "impact":  "Cannot detect crashes or unexpected restarts",
            "action":  "Add app_uptime_seconds gauge metric. "
                       "Set up Alertmanager to notify on restart events.",
            "priority": "Medium",
        })

    # Performance issues
    if perf.get("classification") == "Slow":
        actions.append({
            "problem": f"API response time is slow ({perf.get('avg_ms')} ms average, p95: {perf.get('p95_ms')} ms)",
            "impact":  "Users are experiencing delays — risk of abandonment and lost revenue",
            "action":  "Profile slow endpoints, optimize database queries, add Redis caching. "
                       "Use Grafana to identify the slowest endpoints. Scale backend if needed.",
            "priority": "High",
        })
    elif perf.get("classification") == "Moderate":
        actions.append({
            "problem": f"API response time is moderate ({perf.get('avg_ms')} ms average)",
            "impact":  "Users may notice delays during peak traffic hours",
            "action":  "Review slow database queries and consider adding a caching layer. "
                       "Set Alertmanager alert if p95 exceeds 1 second.",
            "priority": "Medium",
        })

    # Error issues
    if err_a.get("status") == "Critical":
        actions.append({
            "problem": f"Critical error rate — {err_a.get('error_rate_pct')}% of requests failing",
            "impact":  "Users are experiencing failures — direct revenue and trust impact",
            "action":  "Check application logs immediately. Review recent deployments. "
                       "Consider rollback if issue started after a release. "
                       "Use Sentry for detailed error tracking.",
            "priority": "Critical",
        })
    elif err_a.get("status") == "Warning":
        actions.append({
            "problem": f"Elevated error rate — {err_a.get('error_rate_pct')}% of requests failing",
            "impact":  "Some users are experiencing errors",
            "action":  "Review error logs and identify root cause. "
                       "Set up Sentry for error tracking and Alertmanager for alerts.",
            "priority": "Medium",
        })

    # Memory issues
    if res.get("memory_cat") == "High":
        actions.append({
            "problem": f"High memory usage — {res.get('memory_mb'):.0f} MB (above 500 MB threshold)",
            "impact":  "Risk of application crash and complete downtime for all users",
            "action":  "Restart service as emergency measure. Investigate memory leaks. "
                       "Consider increasing server memory allocation. "
                       "Use memory profiling tools to find the leak.",
            "priority": "High",
        })
    elif res.get("memory_cat") == "Moderate":
        actions.append({
            "problem": f"Moderate memory usage — {res.get('memory_mb'):.0f} MB (200–500 MB range)",
            "impact":  "May increase under load — risk of future memory pressure",
            "action":  "Monitor memory trend in Grafana. "
                       "Set Alertmanager alert at 400 MB. "
                       "Review application for unnecessary object retention.",
            "priority": "Low",
        })

    # CPU issues
    if res.get("cpu_cat") == "High":
        actions.append({
            "problem": f"High CPU usage — {res.get('cpu_percent')}% (above 90% threshold)",
            "impact":  "Server may become unresponsive under load",
            "action":  "Scale up server resources immediately. "
                       "Profile application to find CPU-intensive operations. "
                       "Consider horizontal scaling (multiple instances).",
            "priority": "High",
        })
    elif res.get("cpu_cat") == "Moderate":
        actions.append({
            "problem": f"Moderate CPU usage — {res.get('cpu_percent')}%",
            "impact":  "Performance may degrade during traffic spikes",
            "action":  "Plan for capacity increase. Review background jobs. "
                       "Set Alertmanager alert at 80% CPU threshold.",
            "priority": "Low",
        })

    # GC issues
    if gc_a.get("status") in ("Critical", "Warning"):
        actions.append({
            "problem": f"Memory cleanup issues — {gc_a.get('uncollectable')} uncollectable objects",
            "impact":  "Possible memory leak causing gradual performance degradation",
            "action":  "Engineering team should review code for circular references and memory leaks. "
                       "Use Python memory profiler (memory_profiler, objgraph) to identify the source.",
            "priority": "Medium",
        })

    # FD issues
    if stab.get("fd_label") in ("🔴", "⚠️"):
        actions.append({
            "problem": f"High file descriptor usage — {stab.get('fd_pct')}%",
            "impact":  "Application may fail to open new connections or files",
            "action":  "Check for connection leaks (unclosed DB connections, HTTP clients). "
                       "Increase OS file descriptor limits if needed (ulimit -n).",
            "priority": "Medium",
        })

    # Stability issues
    if stab.get("uptime_label") == "⚠️":
        actions.append({
            "problem": f"Recent application restart detected (uptime: {stab.get('uptime')})",
            "impact":  "Users may have experienced a brief outage",
            "action":  "Review application logs to determine cause of restart. "
                       "Set up Alertmanager to notify on unexpected restarts. "
                       "Implement health checks and auto-recovery.",
            "priority": "Medium",
        })

    # Always add a low-priority monitoring improvement action
    actions.append({
        "problem": "Ongoing monitoring and alerting hygiene",
        "impact":  "Without proactive monitoring, issues are discovered only after users complain",
        "action":  "Set up Grafana dashboards for all key metrics. "
                   "Configure Alertmanager for CPU > 80%, memory > 400 MB, error rate > 1%, p95 > 1s. "
                   "Review dashboards weekly with the team.",
        "priority": "Low",
    })

    return actions


# ── Section 11: Final Status ──────────────────────────────────────────────────

def build_final_status(perf, err_a, res, gc_a, stab, km) -> dict:
    missing = km.get("missing_metrics", [])

    critical = (
        perf.get("classification") == "Slow" or
        err_a.get("status") == "Critical" or
        res.get("memory_cat") == "High" or
        res.get("cpu_cat") == "High" or
        gc_a.get("status") == "Critical"
    )
    warning = (
        perf.get("classification") in ("Moderate", "Unknown") or
        err_a.get("status") in ("Warning", "No Data") or
        res.get("memory_cat") == "Moderate" or
        res.get("cpu_cat") == "Moderate" or
        gc_a.get("status") == "Warning" or
        stab.get("uptime_label") == "⚠️" or
        len(missing) > 0
    )

    # Build justification sentence
    reasons = []
    if perf.get("classification") == "Slow":
        reasons.append(f"slow API responses ({perf.get('avg_ms')} ms)")
    if perf.get("classification") == "Unknown":
        reasons.append("missing latency data")
    if err_a.get("status") == "Critical":
        reasons.append(f"critical error rate ({err_a.get('error_rate_pct')}%)")
    if err_a.get("status") in ("Warning", "No Data"):
        reasons.append("error monitoring issues")
    if res.get("memory_cat") == "High":
        reasons.append(f"high memory usage ({res.get('memory_mb'):.0f} MB)")
    if res.get("memory_cat") == "Moderate":
        reasons.append(f"moderate memory usage ({res.get('memory_mb'):.0f} MB)")
    if res.get("cpu_cat") in ("High", "Moderate"):
        reasons.append(f"{res.get('cpu_cat', '').lower()} CPU usage ({res.get('cpu_percent')}%)")
    if missing:
        reasons.append(f"missing monitoring data ({', '.join(missing)})")
    if stab.get("uptime_label") == "⚠️":
        reasons.append("recent application restart")

    if critical:
        justification = "Critical — " + "; ".join(reasons) + ". Immediate action required."
        return {
            "status": "Critical", "icon": "❌", "label": "❌ Critical",
            "color": "#e74c3c",
            "message": (
                f"The system has critical issues requiring immediate attention. "
                f"Reason: {justification} "
                "Users are likely being impacted right now. "
                "Escalate to the engineering team immediately."
            ),
            "justification": justification,
        }
    elif warning:
        justification = "Needs Attention — " + "; ".join(reasons) + "." if reasons else \
                        "Needs Attention — some metrics need monitoring."
        return {
            "status": "Needs Attention", "icon": "⚠️", "label": "⚠️ Needs Attention",
            "color": "#e67e22",
            "message": (
                f"The system is running but requires attention. "
                f"Reason: {justification} "
                "No immediate crisis, but the team should review and address the items below."
            ),
            "justification": justification,
        }
    else:
        return {
            "status": "Healthy", "icon": "✅", "label": "✅ Healthy",
            "color": "#27ae60",
            "message": (
                "All systems are operating normally. "
                "All key metrics are within healthy ranges. "
                "Users are having a good experience. "
                "Continue routine monitoring with Grafana and Alertmanager."
            ),
            "justification": "All metrics within acceptable thresholds.",
        }


# ── Master analyzer ───────────────────────────────────────────────────────────

def analyze_all(raw: dict) -> dict:
    def safe(fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            return {"error": str(e)}

    km   = safe(build_key_metrics,     raw)
    pf   = safe(build_performance,     raw)
    ea   = safe(build_error_analysis,  raw)
    res  = safe(build_resource_analysis, raw)
    gc_a = safe(build_gc_analysis,     raw)
    stb  = safe(build_stability,       raw)

    try:
        biz = build_business_impact(pf, ea, res, gc_a, stb, km)
    except Exception as e:
        biz = [f"Error: {e}"]

    try:
        actions = build_actions(pf, ea, res, gc_a, stb, km)
    except Exception as e:
        actions = []

    try:
        final = build_final_status(pf, ea, res, gc_a, stb, km)
    except Exception as e:
        final = {"status": "Unknown", "icon": "❓", "label": "❓ Unknown",
                 "color": "#95a5a6", "message": str(e), "justification": str(e)}

    # Executive summary — Section 2
    fs = final["status"]
    missing = km.get("missing_metrics", [])
    if fs == "Critical":
        exec_summary = (
            f"🔴 Overall Health: Critical. "
            f"{final.get('justification', '')} "
            "Business operations are being impacted. "
            "The engineering team must act immediately."
        )
    elif fs == "Needs Attention":
        reasons_str = final.get("justification", "some areas need attention")
        exec_summary = (
            f"⚠️ Overall Health: Needs Attention. "
            f"The system is running but has issues: {reasons_str} "
            "No immediate outage, but the team should review and address these items "
            "to prevent future problems."
        )
    else:
        exec_summary = (
            "✅ Overall Health: Good. "
            "All systems are operating normally and within healthy thresholds. "
            "Users are experiencing good performance with no significant errors. "
            "No immediate action is required. "
            "Continue monitoring with Grafana and review dashboards regularly."
        )

    return {
        "instance":          raw["instance"],
        "job":               raw["job"],
        "time_range":        raw["time_range"],
        "fetched_at":        raw["fetched_at"],
        "executive_summary": exec_summary,
        "key_metrics":       km,
        "performance":       pf,
        "error_analysis":    ea,
        "resource":          res,
        "gc_analysis":       gc_a,
        "stability":         stb,
        "business_impact":   biz,
        "actions":           actions,
        "final_status":      final,
        "_raw":              raw,
    }
