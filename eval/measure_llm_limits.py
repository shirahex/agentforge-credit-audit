"""Measures the limits of the configured LLM provider and proposes LLM_MIN_INTERVAL_SECONDS (task I4).

    python eval/measure_llm_limits.py            reads backend/.env, sends a few small calls
    python eval/measure_llm_limits.py --burst 40 sends up to 40 calls without pause to find the per-minute cap

What it reports:
  * the rate-limit headers of the provider (Groq and OpenAI-compatible servers return x-ratelimit-*),
  * latency and tokens of one real audit of each demo file (calls, prompt and completion tokens),
  * with --burst, the number of calls accepted before the first HTTP 429,
  * the interval between calls that keeps an audit under the per-minute caps, as a line for backend/.env.

Without a provider it stops with a message: nothing is estimated from memory.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="agentforge-limits-")

import httpx  # noqa: E402

from app import config  # noqa: E402
from app.graph import trace  # noqa: E402
from app.graph.build import graph  # noqa: E402
from app.llm import client  # noqa: E402
from app.samples import load_samples, sample  # noqa: E402


def probe() -> tuple[int, dict[str, str], float]:
    base, model = client._endpoint()
    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"
    body = {"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": "Answer with the word ok."}]}
    started = time.perf_counter()
    resp = httpx.post(f"{base}/chat/completions", json=body, headers=headers, timeout=config.LLM_TIMEOUT_SECONDS)
    limits = {k: v for k, v in resp.headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
    return resp.status_code, limits, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--burst", type=int, default=0, help="calls sent without pause to find the per-minute cap")
    args = parser.parse_args()
    if not client.enabled():
        raise SystemExit("LLM_PROVIDER is `none`. Set a provider and a key in backend/.env, then run again.")
    base, model = client._endpoint()
    print(f"Provider {config.LLM_PROVIDER}, model {model}, endpoint {base}\n")

    status, limits, seconds = probe()
    print(f"Probe call: HTTP {status} in {seconds:.2f} s")
    for k, v in sorted(limits.items()):
        print(f"  {k}: {v}")
    if status != 200:
        raise SystemExit("The provider refused the probe call: check the key and the model name.")
    if not limits:
        print("  no rate-limit header returned: read the limits of this model in the provider's console")

    accepted = None
    if args.burst:
        accepted = 0
        for _ in range(args.burst):
            code, _, _ = probe()
            if code == 429:
                break
            accepted += 1
        print(f"\nBurst: {accepted} calls accepted before the first 429" if accepted < args.burst
              else f"\nBurst: {accepted} calls accepted, no 429")
        print("Waiting 60 s for the per-minute window to reset.")
        time.sleep(60)

    print("\nOne audit of each demo file (current LLM_MIN_INTERVAL_SECONDS = "
          f"{config.LLM_MIN_INTERVAL_SECONDS:g}):")
    rows = []
    for s in load_samples():
        started = time.perf_counter()
        out = graph.invoke({"application": sample(s["tag"])})
        t = trace.summarise(out["trail"])
        rows.append((s["tag"], t["llm_calls"], t["prompt_tokens"], t["completion_tokens"], t["fallback_steps"],
                     t["llm_steps"], time.perf_counter() - started))
        print(f"  {s['tag']:15s} {t['llm_calls']:2d} calls  {t['prompt_tokens']:5d} prompt + {t['completion_tokens']:4d} "
              f"completion tokens  {t['fallback_steps']} of {t['llm_steps']} steps fell back to rules  {rows[-1][-1]:5.1f} s")
    if client.USAGE.last_error:
        print(f"  last error: {client.USAGE.last_error}")
    calls = sum(r[1] for r in rows) or 1
    tokens_per_call = sum(r[2] + r[3] for r in rows) / calls

    def header(*names: str) -> float | None:
        for name in names:
            for k, v in limits.items():
                if k.lower() == name:
                    try:
                        return float(v)
                    except ValueError:
                        pass
        return None

    tpm = header("x-ratelimit-limit-tokens")
    rpm = accepted if accepted and accepted < args.burst else None
    interval = 0.0
    if tpm:
        interval = max(interval, 60 * tokens_per_call / tpm)
    if rpm:
        interval = max(interval, 60 / rpm)
    print(f"\nMean tokens per call: {tokens_per_call:.0f}")
    if interval:
        print(f"Tokens per minute allowed: {tpm:.0f}" if tpm else "", f"Calls per minute observed: {rpm}" if rpm else "")
        print(f"\nLine for backend/.env:\nLLM_MIN_INTERVAL_SECONDS={interval * 1.15:.1f}")
    else:
        print("No per-minute cap could be read. Use: interval = max(60 / RPM, 60 * tokens per call / TPM), "
              "with the RPM and TPM shown for this model in the provider's console.")


if __name__ == "__main__":
    main()
