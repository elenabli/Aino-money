import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_extra = os.getenv("OPENAI_EXTRA_HEADERS", "{}")
try:
    OPENAI_EXTRA_HEADERS: dict[str, str] = json.loads(_extra)
except json.JSONDecodeError:
    OPENAI_EXTRA_HEADERS = {}

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6"
ANTHROPIC_WORKSPACE_ID = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()

CHAT_PROVIDER = os.getenv("CHAT_PROVIDER") or ("anthropic" if ANTHROPIC_API_KEY else "openai")
if CHAT_PROVIDER not in {"anthropic", "openai"}:
    raise ValueError("CHAT_PROVIDER must be anthropic or openai")

if CHAT_PROVIDER == "anthropic":
    CHAT_API_KEY = ANTHROPIC_API_KEY
    CHAT_MODEL = ANTHROPIC_MODEL
    CHAT_BASE_URL = "https://api.anthropic.com/v1/"
    CHAT_HEADERS = {"anthropic-workspace-id": ANTHROPIC_WORKSPACE_ID} if ANTHROPIC_WORKSPACE_ID else {}
else:
    CHAT_API_KEY = OPENAI_API_KEY
    CHAT_MODEL = OPENAI_MODEL
    CHAT_BASE_URL = OPENAI_BASE_URL
    CHAT_HEADERS = OPENAI_EXTRA_HEADERS

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
TYPESAFE_MODEL = os.getenv("TYPESAFE_MODEL", "jev-latest")

DEMO_CUSTOMER_ID = os.getenv("DEMO_CUSTOMER_ID", "CUST00001")

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "spanki.duckdb"
JEV_CACHE_PATH = DATA_DIR / "jev_merchant_cache.json"

TX_PATH = ROOT.parent / "tx_junction_transactions.txt"
CUSTOMERS_PATH = ROOT.parent / "tx_customers_junction.csv"

JEV_CONFIDENCE_FLOOR = float(os.getenv("JEV_CONFIDENCE_FLOOR", "0.7"))
