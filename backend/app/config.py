import os
from pathlib import Path

_env = Path(__file__).resolve().parents[1] / ".env"
if _env.exists():  # minimal .env loader, no extra dependency
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

# Model under audit: "full" uses every attribute, "unaware" drops the protected ones.
MODEL_VARIANT = os.getenv("MODEL_VARIANT", "full")
# Refusal threshold on the default probability. Empty: the cost-optimal value stored with the model.
REFUSAL_THRESHOLD = float(os.environ["REFUSAL_THRESHOLD"]) if os.getenv("REFUSAL_THRESHOLD") else None
# Scores inside this band around the threshold go to a human reviewer.
BORDERLINE_MARGIN = float(os.getenv("BORDERLINE_MARGIN", "0.02"))
# A counterfactual is robust when it clears the threshold by at least this margin.
ROBUST_MARGIN = float(os.getenv("ROBUST_MARGIN", "0.02"))
# Maximum number of counterfactual generation attempts before escalation.
MAX_CF_ATTEMPTS = int(os.getenv("MAX_CF_ATTEMPTS", "3"))
SENSITIVE_FEATURES = ("sex", "foreign_worker")
# Pause between agents so the interface can show progress (seconds).
STEP_DELAY_SECONDS = float(os.getenv("STEP_DELAY_SECONDS", "0.7"))

# LLM access. Provider "none" keeps every agent on its deterministic rules.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()  # none | gemini | groq | ollama | openai_compatible
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_MIN_INTERVAL_SECONDS = float(os.getenv("LLM_MIN_INTERVAL_SECONDS", "0"))

# --- Fairness audit (task I1)
# Age bands used for the group metrics: upper bounds, inclusive. The last band is open.
AGE_BANDS = ((25, "18-25"), (40, "26-40"), (200, "41+"))
# A gap in approval rate above this value between two groups is reported as a disparity.
FAIRNESS_TOLERANCE = float(os.getenv("FAIRNESS_TOLERANCE", "0.10"))
# Groups with fewer test files than this are shown but never trigger an alert.
FAIRNESS_MIN_GROUP = int(os.getenv("FAIRNESS_MIN_GROUP", "20"))
# Plausibility of a counterfactual: mean Gower distance to its k nearest training files, compared
# with the same distance measured for every training file. Beyond this quantile it is an outlier.
PLAUSIBILITY_K = int(os.getenv("PLAUSIBILITY_K", "5"))
PLAUSIBILITY_QUANTILE = float(os.getenv("PLAUSIBILITY_QUANTILE", "0.95"))
# An applicant who is already unusual is not blamed for it: a counterfactual beyond the limit is only
# rejected when the changes themselves moved the file away by more than this (about half an attribute).
PLAUSIBILITY_SLACK = float(os.getenv("PLAUSIBILITY_SLACK", "0.03"))

# --- Durable state (tasks I3 and I4): checkpoints, runs, case store, traces and PDF reports.
DATA_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
