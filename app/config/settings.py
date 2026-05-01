from pydantic_settings import BaseSettings
from pathlib import Path

# resolves to Dashathon-PAE/.env no matter where main.py runs from
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

class Settings(BaseSettings):
    ENVIRONMENT:           str = "local"
    ORCHESTRATOR_BASE_URL: str = "http://0.0.0.0:3016"
    MEF_BASE_URL:          str = "http://0.0.0.0:3027"
    ORCHESTRATOR_API_KEY:  str = "dev-key"

    model_config = {"env_file": str(ENV_FILE), "env_file_encoding": "utf-8"}

settings = Settings()
