# EMS Backend — Prometheus Metrics Reporting API

## Folder Structure

```
ems-backend/
├── app/
│   ├── __init__.py
│   ├── metrics_fetcher.py   # Fetches raw metrics from Prometheus
│   ├── analyzer.py          # Analyzes metrics, generates alerts/suggestions
│   ├── report_generator.py  # Builds TXT / HTML / PDF reports
│   └── api.py               # FastAPI endpoints
├── config.py                # Prometheus URL + thresholds
├── main.py                  # Server entry point
├── requirements.txt
└── README.md
```

---

## Setup

```bash
cd ems-backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Set your Prometheus URL (default is localhost:9090):

```bash
export PROMETHEUS_URL=http://your-prometheus-host:9090
```

Start the server:

```bash
python main.py
# OR
uvicorn main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs

---

## API Endpoints

### GET /projects
Discover all active Prometheus targets.

```
GET http://localhost:8000/projects
```

### GET /report
Get a full JSON analysis report.

```
GET http://localhost:8000/report?instance=climateye-apis.up.railway.app&job=Climateeye_api&time_range=6h
```

Custom time range:
```
GET http://localhost:8000/report?instance=...&job=...&time_range=custom&start_time=2024-01-01T00:00:00Z&end_time=2024-01-01T06:00:00Z
```

### GET /download/txt
```
GET http://localhost:8000/download/txt?instance=...&job=...&time_range=24h
```

### GET /download/html
```
GET http://localhost:8000/download/html?instance=...&job=...&time_range=24h
```

### GET /download/pdf
```
GET http://localhost:8000/download/pdf?instance=...&job=...&time_range=24h
```

---

## Frontend PDF Download Button

```html
<a href="http://localhost:8000/download/pdf?instance=myapp.railway.app&job=my_api&time_range=24h"
   download>
  Download PDF Report
</a>
```

Or with JavaScript fetch:

```javascript
async function downloadPDF(instance, job, timeRange) {
  const url = `http://localhost:8000/download/pdf?instance=${instance}&job=${job}&time_range=${timeRange}`;
  const res = await fetch(url);
  const blob = await res.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `ems_report_${job}_${timeRange}.pdf`;
  link.click();
}
```

---

## Adding New Metrics

1. Add a new `fetch_*` function in `metrics_fetcher.py`
2. Add a new `analyze_*` function in `analyzer.py`
3. Call both in `fetch_all_metrics()` and `analyze_all()`
4. Add the new section to all three report generators in `report_generator.py`

## Adding New Projects

No code changes needed — just point Prometheus at the new target and use its
`instance` + `job` labels in the API query params.
