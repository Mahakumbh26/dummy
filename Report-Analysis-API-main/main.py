# main.py
# Entry point for the EMS backend server.
# Run with: python main.py
#       OR: uvicorn main:app --reload --port 8000

import sys
import os

# Put both the project root (for config.py) and app/ (for module imports) on the path
ROOT = os.path.dirname(__file__)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

from app.api import app  # noqa: F401 — re-exported for uvicorn

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
