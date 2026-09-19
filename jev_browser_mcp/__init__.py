"""browser_harness reads these at import time, so they must be set before jev_ultrafast loads."""

import os

CDP_PORT = int(os.environ.get("JEV_CDP_PORT", "9333"))

os.environ.setdefault("BU_CDP_URL", f"http://127.0.0.1:{CDP_PORT}")
os.environ.setdefault("BU_NAME", "jev-mcp")
os.environ.setdefault("BH_TELEMETRY", "0")
os.environ.setdefault("BH_UPDATE_CHECK", "0")
