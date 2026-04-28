import uvicorn
from tests.emulator.pae_emulator import app as pae_app

if __name__ == "__main__":
    print("PAE emulator running on http://127.0.0.1:3016")
    print("Swagger UI: http://127.0.0.1:3016/docs")
    print("Press CTRL+C to stop...\n")
    uvicorn.run(pae_app, host="127.0.0.1", port=3016, log_level="info")