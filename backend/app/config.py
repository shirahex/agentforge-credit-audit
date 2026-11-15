import os

# Decision threshold on the default probability.
REFUSAL_THRESHOLD = float(os.getenv("REFUSAL_THRESHOLD", "0.5"))
# Scores inside this band around the threshold go to a human reviewer.
BORDERLINE_MARGIN = float(os.getenv("BORDERLINE_MARGIN", "0.05"))
# Maximum number of counterfactual generation attempts before escalation.
MAX_CF_ATTEMPTS = int(os.getenv("MAX_CF_ATTEMPTS", "3"))
# Features an applicant cannot change, or that must never be suggested.
IMMUTABLE_FEATURES = {"age", "sex", "foreign_worker"}
SENSITIVE_FEATURES = ("sex",)
# Artificial pause between agents so the interface can show progress.
STEP_DELAY_SECONDS = float(os.getenv("STEP_DELAY_SECONDS", "0.6"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none")  # none | gemini | groq | ollama
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
