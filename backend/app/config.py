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
# Second provider, used while the first one is rate limited or unreachable.
LLM_FALLBACK_PROVIDER = os.getenv("LLM_FALLBACK_PROVIDER", "none").lower()
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "")
LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "")
LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY", "")
# Answers already obtained are kept here, so repeating an audit costs no tokens. Empty: no file.
LLM_CACHE_FILE = os.getenv("LLM_CACHE_FILE", str(Path(__file__).resolve().parents[1] / ".llm_cache.json"))
