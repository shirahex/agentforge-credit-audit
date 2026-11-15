"""Test isolation: checkpoints, runs, cases, traces and reports go to a temporary folder."""
import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="agentforge-tests-")
os.environ.setdefault("LLM_PROVIDER", "none")
