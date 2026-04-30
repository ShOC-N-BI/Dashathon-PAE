"""
tests/emulator/pae_run_emulator.py

Starts the combined PAE emulator — your fake orchestrator for local testing.

Usage:
    python tests/emulator/pae_run_emulator.py

Then in your .env set:
    ORCHESTRATOR_BASE_URL=http://127.0.0.1:3016
    ORCHESTRATOR_API_KEY=any-value   (emulator does not check the key)

Swagger UI (explore and trigger endpoints manually):
    http://127.0.0.1:3016/docs

---- HOW TO TEST ----

1. Start the emulator (this file)
2. Start your PAE app:  python main.py
3. Send a reassessment trigger via curl or the Swagger UI:

    curl -X POST http://127.0.0.1:3016/paeinputs \\
      -H "Content-Type: application/json" \\
      -d '{
            "requestId": "test-001",
            "trackId": "AMTI SAT detected TBM launch preparations at grid PB1.2",
            "originator": "test-operator"
          }'

4. Watch your PAE app terminal — it will receive the SSE event,
   run the AI, and POST the result back.

5. Check the result at:
    curl http://127.0.0.1:3016/paeoutputs
"""

import sys
import os

# Ensure project root is on the path so schemas/ and config.py are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import uvicorn
from tests.emulator.pae_combined_emulator import app as pae_app

if __name__ == "__main__":
    print("=" * 60)
    print("PAE Emulator — fake orchestrator for local testing")
    print("=" * 60)
    print("Base URL:   http://127.0.0.1:3016")
    print("Swagger UI: http://127.0.0.1:3016/docs")
    print()
    print("Endpoints:")
    print("  GET  /paeoutputs        — view stored assessments")
    print("  POST /paeoutputs        — your PAE app posts results here")
    print("  POST /paeinputs         — fire a reassessment trigger")
    print("  GET  /paeinputs-sse     — your PAE app listens here")
    print()
    print("Press CTRL+C to stop.\n")
    uvicorn.run(pae_app, host="127.0.0.1", port=3016, log_level="info")
