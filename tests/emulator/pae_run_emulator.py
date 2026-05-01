import uvicorn
from tests.emulator.pae_combined_emulator import app as pae_app

def run_emulator():
    print("PAE emulator running on http://localhost:3016")
    print("Swagger UI: http://localhost:3016/docs")
    print("Handles: GET/POST/PUT /paeoutputs  |  POST /paeinputs  |  GET /paeinputs-sse")
    # print("Press CTRL+C to stop...\n")
    uvicorn.run(pae_app, host="0.0.0.0", port=3016, log_level="info")

if __name__ == "__main__":
    print("PAE emulator running on http://127.0.0.1:3016")
    print("Swagger UI: http://127.0.0.1:3016/docs")
    print("Handles: GET/POST/PUT /paeoutputs  |  POST /paeinputs  |  GET /paeinputs-sse")
    print("Press CTRL+C to stop...\n")
    uvicorn.run(pae_app, host="127.0.0.1", port=3016, log_level="info")
