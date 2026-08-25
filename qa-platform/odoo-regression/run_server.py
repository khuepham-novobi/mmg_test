"""Start the test-runner web application.

    python run_server.py

Then open http://localhost:8000
"""
import uvicorn

from backend.config import settings

if __name__ == "__main__":
    print("=" * 60)
    print("  ODOO REGRESSION TEST RUNNER")
    print(f"  → http://{settings.server_host}:{settings.server_port}")
    print(f"  headless browser: {settings.headless}  "
          f"(set HEADLESS=false in .env to watch)")
    print("=" * 60)
    uvicorn.run("backend.app:app", host=settings.server_host,
                port=settings.server_port, log_level="info")
