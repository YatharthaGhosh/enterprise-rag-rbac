#!/bin/bash
# Start the API privately, wait until it answers, then serve the UI on the Space's public port.
set -e
uvicorn app.api:app --host 127.0.0.1 --port 8000 &
python - <<'PY'
import time, urllib.request
for _ in range(120):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2); break
    except Exception:
        time.sleep(1)
PY
exec streamlit run ui/streamlit_app.py --server.port 7860 --server.address 0.0.0.0 --server.headless true \
    --browser.gatherUsageStats false --server.enableXsrfProtection false
