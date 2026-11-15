"""Finds request settings under which the configured model returns usable JSON (run before --llm).

    python eval/llm_preflight.py

Sends the real prompt of the Modele-Scoring agent for one demo file under a few settings, from the
plainest to the most generous, and keeps the first one whose answer passes the agent's guards. The
retained settings are written to backend/.env (LLM_MAX_TOKENS_SCALE, LLM_EXTRA_BODY). Reasoning
models need a larger answer budget, because their reasoning is counted in max_tokens.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="agentforge-preflight-")

from app import config  # noqa: E402
from app.agents import modele_scoring  # noqa: E402
from app.llm import client  # noqa: E402
from app.samples import sample  # noqa: E402

CANDIDATES = [
    (1.0, {}),
    (4.0, {}),
    (4.0, {"reasoning_effort": "low"}),
    (8.0, {"reasoning_effort": "low"}),
]


def main() -> None:
    if not client.enabled():
        raise SystemExit("LLM_PROVIDER is `none`. Set a provider and a key in backend/.env, then run again.")
    base, model = client._endpoint()
    print(f"Provider {config.LLM_PROVIDER}, model {model}")
    chosen = None
    for scale, extra in CANDIDATES:
        config.LLM_MAX_TOKENS_SCALE, config.LLM_EXTRA_BODY = scale, extra
        client.USAGE.last_error = ""
        before = (client.USAGE.calls, client.USAGE.prompt_tokens, client.USAGE.completion_tokens)
        out = modele_scoring.run({"application": sample("terms")})
        used = (client.USAGE.calls - before[0], client.USAGE.prompt_tokens - before[1],
                client.USAGE.completion_tokens - before[2])
        print(f"  answer budget x{scale:g}, extra {json.dumps(extra)}: step written by {out['mode']}; "
              f"{used[0]} calls, {used[1]} prompt + {used[2]} completion tokens; "
              f"last error: {client.USAGE.last_error or 'none'}")
        if out["mode"] == "llm":
            chosen = (scale, extra)
            print("  explanation:", out["explanation"])
            break
    if chosen is None:
        raise SystemExit("No setting gave a usable answer. See the errors above.")
    env = ROOT / "backend" / ".env"
    lines = [line for line in env.read_text(encoding="utf-8").splitlines()
             if not line.startswith(("LLM_MAX_TOKENS_SCALE=", "LLM_EXTRA_BODY="))] if env.exists() else []
    lines += [f"LLM_MAX_TOKENS_SCALE={chosen[0]:g}", f"LLM_EXTRA_BODY={json.dumps(chosen[1])}"]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Retained: LLM_MAX_TOKENS_SCALE={chosen[0]:g}, LLM_EXTRA_BODY={json.dumps(chosen[1])} (written to backend/.env)")


if __name__ == "__main__":
    main()
