import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs) -> bool:
        return False


PROJECT_ROOT = Path(__file__).resolve().parent
PARENT_PROJECT_ENV = PROJECT_ROOT.parent.parent / "PMAssistant" / ".env"
load_dotenv(PROJECT_ROOT / ".env")
if PARENT_PROJECT_ENV.exists():
    load_dotenv(PARENT_PROJECT_ENV, override=False)

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")