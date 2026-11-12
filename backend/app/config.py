"""Every tunable number in one place, so each rule can be explained in the demo."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("FOOTNOTE_DATA") or os.environ.get("HOOKLINE_DATA") or (ROOT / "data"))
CACHE = DATA / "cache"          # recorded answers: reused only within one run, or by the offline test set
DB = DATA / "runs.db"


def _load_env():
    env = ROOT.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()

CRUSTDATA_KEY = os.environ.get("CRUSTDATA_API_KEY", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()

# "live": every prospect is looked up fresh in Crustdata and written fresh by the model.
# "replay": answer only from recorded responses (used by the offline test set).
DEFAULT_MODE = os.environ.get("FOOTNOTE_MODE") or os.environ.get("HOOKLINE_MODE") or "replay"
ACCESS_CODE = (os.environ.get("FOOTNOTE_ACCESS_CODE") or "").strip()   # required for live runs when set

# Credit guards (Crustdata bills per call, and per result on searches)
RUN_CREDIT_CAP = float(os.environ.get("RUN_CREDIT_CAP", "6"))
DAILY_CREDIT_CAP = float(os.environ.get("DAILY_CREDIT_CAP", "0"))   # 0 = no daily limit
RUNS_PER_VISITOR = int(os.environ.get("RUNS_PER_VISITOR", "0"))   # new prospects per visitor per day; 0 = no limit
PEOPLE_PER_SEARCH = 5
JOBS_PER_SEARCH = 6

# Signal rules
STALE_DAYS = 180              # older than this can be context, never the hook
NEWS_WINDOW_DAYS = 120        # news older than this is not gathered at all
CROWDED_OUTLETS = 5           # an event covered by this many outlets is "crowded"
CROWDED_PENALTY = 1.5         # points off the hook score (scale 0-5)
NEW_ROLE_WINDOW = (21, 150)   # days in a role when a new leader is choosing tools
RECONTACT_DAYS = 30           # same person drafted within this many days -> warn

# Hook score weights (sum to 1); each part is 0-5
W_RELEVANCE, W_RECENCY, W_PERSONAL, W_SOURCE = 0.40, 0.25, 0.20, 0.15
MIN_HOOK_SCORE = 2.4          # best hook below this -> "low signal"

# Draft rules
MAX_WORDS = 100
BANNED = ["i hope this finds you well", "i came across your profile", "i wanted to reach out",
          "i noticed", "i came across", "congrats on", "congratulations on", "game-changer", "game changer",
          "synergy", "revolutionize", "cutting-edge", "in today's fast-paced", "touch base",
          "just checking in", "quick question"]

LLM_MODELS = [
    {"name": "gemini-pro-latest", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "key": GEMINI_KEY},
    {"name": "deepseek-flash", "base": "https://api.deepseek.com", "key": DEEPSEEK_KEY},
]
