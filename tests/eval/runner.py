"""Eval runner for the context-overflow fallback.

    python -B -m tests.eval.runner [--models M ...] [--variants V ...] [--fixtures F ...]
                                   [--out docs/eval-results.json] [--report docs/EVAL-RESULTS.md]
                                   [--no-resume] [--report-only]

Runs each (model, variant, fixture) cell once at temperature 0 against a real Ollama, with a fresh runner and
event store per cell, and records whether the answer sentence reached the derived text, the final answer,
whether it was correct, the model calls made and the wall time. Results are saved after every cell, so a long
run can be resumed. Thresholds and the winner rule are declared in PLAN.md (T5) and implemented below.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests import support  # noqa: F401,E402
from tests.eval.fixtures import FIXTURE_NAMES, MAX_REPLY_TOKENS, NUM_CTX, all_fixtures  # noqa: E402
from agent_harness.config import BackendConfig, Timeouts  # noqa: E402
from agent_harness.conversation.generation import GenerationRunner  # noqa: E402
from agent_harness.conversation.manager import ConversationManager  # noqa: E402
from agent_harness.conversation.provenance import COMPOSITIONS  # noqa: E402
from agent_harness.models.ollama import OllamaBackend  # noqa: E402
from agent_harness.models.registry import ModelRegistry  # noqa: E402
from agent_harness.models.transport import Transport  # noqa: E402
from agent_harness.store.event_store import EventStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MODELS = ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen3.5:2b", "qwen3.5:4b", "qwen3.5:9b")
VARIANTS = tuple(COMPOSITIONS)
MODEL_SIZE_B = {"qwen2.5:0.5b": 0.5, "qwen2.5:1.5b": 1.5, "qwen3.5:2b": 2.0, "qwen3.5:4b": 4.0, "qwen3.5:9b": 9.0}
# Fixed before the first run (PLAN.md, T5). Each is a pass rate over the fixtures of one model.
THRESHOLDS = {"extraction_models_ge_1_5b": 1.0, "extraction_0_5b": 7 / 8, "correctness_models_ge_4b": 0.8}
SYSTEM_PROMPT = ("Read the user's final Question: section and answer with only the requested value. "
                 "Do not quote or summarize the context.")
CHECKS = ("extraction_models_ge_1_5b", "extraction_0_5b", "correctness_models_ge_4b", "absent_fact_fails_visibly")


def norm(text: str) -> str:
    return " ".join(text.split())


def run_cell(backend, model: str, fixture, variant: str, timeout: float = 600) -> dict:
    """One run. Never raises for a model or backend failure: that is a result."""
    with tempfile.TemporaryDirectory(prefix="agent-harness-eval-") as directory:
        store = EventStore(Path(directory) / "events.sqlite3")
        calls = [0]
        real_chat = backend.chat

        def counting(*args, **kwargs):
            calls[0] += 1
            return real_chat(*args, **kwargs)

        backend.chat = counting
        try:
            conversations = ConversationManager(store)
            conversation = conversations.create()
            runner = GenerationRunner(conversations, ModelRegistry([backend]), system_prompt=SYSTEM_PROMPT,
                                      num_ctx=NUM_CTX, reply_tokens=MAX_REPLY_TOKENS,
                                      options={"temperature": 0}, overflow_composition=variant)
            started = time.monotonic()
            generation = runner.send(conversation, fixture.text, f"{backend.config.id}:{model}")
            finished = generation.finished.wait(timeout)
            seconds = time.monotonic() - started
            snapshot = generation.snapshot()
            state = snapshot["state"] if finished else "timeout"
            reason = (snapshot["error"] or {}).get("reason", "") if state == "failed" else ""
            answer = snapshot["text"] if state == "done" else ""
            derived = ((conversations.get(conversation)["window"] or {}).get("derived")) if state == "done" else None
        finally:
            backend.chat = real_chat
            store.close()
    visible = state == "failed" and reason == "context_exceeded" and not snapshot["text"]
    if fixture.expect_failure:  # nothing should be extracted for a fact that is not there
        extraction_ok, correct = visible, visible
    else:
        extraction_ok = bool(derived) and all(norm(f) in norm(derived["text"]) for f in fixture.facts)
        correct = state == "done" and all(key.lower() in answer.lower() for key in fixture.answers)
    return {"variant": variant, "model": model, "fixture": fixture.name, "state": state, "error_reason": reason,
            "answer": answer, "derived": bool(derived), "extraction_ok": extraction_ok, "correct": correct,
            "visible_failure": visible, "model_calls": calls[0], "seconds": round(seconds, 2)}


def _save(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(path.name + ".tmp")
    scratch.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.replace(scratch, path)


def run_matrix(backend, models, variants, fixtures, out, progress=None, resume: bool = True) -> dict:
    path = Path(out)
    doc = json.loads(path.read_text(encoding="utf-8")) if resume and path.exists() else {"meta": {}, "cells": []}
    doc["meta"] = {**doc.get("meta", {}), "num_ctx": NUM_CTX, "reply_tokens": MAX_REPLY_TOKENS,
                   "temperature": 0, "runs_per_cell": 1, "thresholds_declared_in": "PLAN.md T5 (commit 533ef38)",
                   "updated": datetime.now().isoformat(timespec="seconds")}
    done = {(c["variant"], c["model"], c["fixture"]) for c in doc["cells"]}
    for model in models:
        for variant in variants:
            for fixture in fixtures:
                if (variant, model, fixture.name) in done:
                    continue
                cell = run_cell(backend, model, fixture, variant)
                doc["cells"].append(cell)
                _save(path, doc)
                if progress:
                    progress(cell)
    doc = finish(doc)
    _save(path, doc)
    return doc


def _rate(rows: list[dict], key: str) -> tuple[int, int]:
    return sum(bool(c[key]) for c in rows), len(rows)


def evaluate_thresholds(cells: list[dict], variant: str) -> dict:
    rows = [c for c in cells if c["variant"] == variant]
    by_model = {m: [c for c in rows if c["model"] == m] for m in MODELS}

    def all_pass(models, key, threshold):
        detail, met = {}, bool(models)
        for model in models:
            passed, total = _rate(by_model[model], key)
            detail[model] = f"{passed}/{total}"
            met = met and total > 0 and passed / total >= threshold
        return {"met": met, "detail": detail}

    big_extraction = [m for m in MODELS if MODEL_SIZE_B[m] >= 1.5]
    big_correct = [m for m in MODELS if MODEL_SIZE_B[m] >= 4]
    absent = [c for c in rows if c["fixture"] == "absent_fact"]
    checks = {
        "extraction_models_ge_1_5b": all_pass(big_extraction, "extraction_ok", THRESHOLDS["extraction_models_ge_1_5b"]),
        "extraction_0_5b": all_pass(["qwen2.5:0.5b"], "extraction_ok", THRESHOLDS["extraction_0_5b"]),
        "correctness_models_ge_4b": all_pass(big_correct, "correct", THRESHOLDS["correctness_models_ge_4b"]),
        "absent_fact_fails_visibly": {"met": bool(absent) and all(c["visible_failure"] for c in absent),
                                      "detail": {c["model"]: c["visible_failure"] for c in absent}},
    }
    report_only = {"correctness": {m: "%d/%d" % _rate(by_model[m], "correct") for m in MODELS
                                   if MODEL_SIZE_B[m] < 4 and by_model[m]}}
    timings = {m: {"seconds": round(sum(c["seconds"] for c in by_model[m]), 2),
                   "calls": sum(c["model_calls"] for c in by_model[m])} for m in MODELS if by_model[m]}
    return {"checks": checks, "report_only": report_only, "timings": timings}


def choose_winner(cells: list[dict]) -> dict:
    """Winner rule (PLAN.md, T5): most thresholds met, then most correct answers, then most extraction passes,
    then fewest model calls, then the baseline."""
    scores = {}
    for variant in [v for v in VARIANTS if any(c["variant"] == v for c in cells)]:
        rows = [c for c in cells if c["variant"] == variant]
        checks = evaluate_thresholds(cells, variant)["checks"]
        scores[variant] = {"thresholds_met": sum(check["met"] for check in checks.values()),
                           "correct": sum(bool(c["correct"]) for c in rows),
                           "extraction": sum(bool(c["extraction_ok"]) for c in rows),
                           "model_calls": sum(c["model_calls"] for c in rows)}
    winner = max(scores, key=lambda v: (scores[v]["thresholds_met"], scores[v]["correct"], scores[v]["extraction"],
                                        -scores[v]["model_calls"], 1 if v == "baseline" else 0))
    return {"winner": winner, "scores": scores}


def finish(doc: dict) -> dict:
    cells = doc["cells"]
    doc["thresholds"] = {v: evaluate_thresholds(cells, v) for v in VARIANTS if any(c["variant"] == v for c in cells)}
    doc.update(choose_winner(cells) if cells else {"winner": None, "scores": {}})
    return doc


def _code(cell: dict) -> str:
    return "E%s C%s %dc %ds" % ("+" if cell["extraction_ok"] else "-", "+" if cell["correct"] else "-",
                                cell["model_calls"], round(cell["seconds"]))


def render_report(doc: dict) -> str:
    cells, winner = doc["cells"], doc.get("winner")
    lines = ["# Overflow fallback eval", "",
             "Generated by `python -B -m tests.eval.runner`. One run per cell at temperature 0, `num_ctx` "
             f"{NUM_CTX}, reply limit {MAX_REPLY_TOKENS}, fresh runner and event store per cell. Thresholds, the "
             "interpretation of them and the winner rule were fixed in PLAN.md (T5) before the first run.", "",
             "Cell code: `E+`/`E-` the answer sentence(s) reached the derived text (for the absent-fact fixture: "
             "failed visibly), `C+`/`C-` the final answer was correct (absent fact: failed visibly), `Nc` model "
             "calls, `Ns` wall seconds.", ""]
    lines += [f"Winner: {winner}", ""]
    if doc.get("scores"):
        lines += ["| Variant | Thresholds met (of 4) | Correct answers | Extraction passes | Model calls |", "|---|---|---|---|---|"]
        lines += [f"| {v} | {s['thresholds_met']} | {s['correct']} | {s['extraction']} | {s['model_calls']} |"
                  for v, s in doc["scores"].items()]
        lines.append("")
    lines += ["## Exit thresholds", "",
              "- The answer sentence is in the derived text in 100% of fixtures for models >= 1.5B and >= 7/8 for 0.5B.",
              "- Final-answer correctness >= 80% for models >= 4B (reported, not gated, for smaller).",
              "- The absent-fact fixture fails visibly every time.",
              "- Timings are reported, not gated.", ""]
    for variant, result in doc.get("thresholds", {}).items():
        mark = " (winner)" if variant == winner else ""
        lines += [f"### {variant}{mark}", "", "| Check | Met | Detail |", "|---|---|---|"]
        for name in CHECKS:
            check = result["checks"][name]
            lines.append(f"| {name} | {'yes' if check['met'] else 'NO'} | "
                         f"{', '.join(f'{k}: {v}' for k, v in check['detail'].items())} |")
        if result["report_only"]["correctness"]:
            lines += ["", "Correctness for models below 4B (reported only): " + ", ".join(
                f"{m} {v}" for m, v in result["report_only"]["correctness"].items())]
        lines += ["", "| Model | Total seconds | Total model calls |", "|---|---|---|"]
        lines += [f"| {m} | {t['seconds']} | {t['calls']} |" for m, t in result["timings"].items()]
        lines.append("")
    lines += ["## Silent wrong answers", "",
              "Replies that completed normally, with no error and no warning, but whose answer did not contain the "
              "expected key. A user would see a confident answer. \"Passage in derived text\" says whether extraction "
              "had found the answer sentence (no: extraction found some passages but not the answer).", ""]
    for variant in doc.get("thresholds", {}):
        silent = [c for c in cells if c["variant"] == variant and c["state"] == "done" and not c["correct"]
                  and c["fixture"] != "absent_fact"]
        lines += [f"### {variant}", "", "| Model | Fixture | Passage in derived text | Answer given |", "|---|---|---|---|"]
        lines += [f"| {c['model']} | {c['fixture']} | {'yes' if c['extraction_ok'] else 'no'} | "
                  f"{' '.join(c['answer'].split()).replace('|', '/')[:120]} |" for c in silent] or ["| none | | | |"]
        lines.append("")
    for variant in doc.get("thresholds", {}):
        lines += [f"## Cells: {variant}", "", "| Fixture | " + " | ".join(MODELS) + " |",
                  "|---|" + "---|" * len(MODELS)]
        for name in FIXTURE_NAMES:
            row = []
            for model in MODELS:
                cell = next((c for c in cells if (c["variant"], c["model"], c["fixture"]) == (variant, model, name)), None)
                row.append(_code(cell) if cell else "-")
            lines.append(f"| {name} | " + " | ".join(row) + " |")
        lines.append("")
    if winner and winner in doc.get("thresholds", {}):
        missed = [n for n in CHECKS if not doc["thresholds"][winner]["checks"][n]["met"]]
        lines += ["## Known limitations", ""]
        lines += ([f"- Threshold `{n}` was missed by the winning variant ({winner}); recorded as a known limitation."
                   for n in missed] or ["- None: every exit threshold was met by the winning variant."]) + [""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument("--variants", nargs="+", default=list(VARIANTS))
    parser.add_argument("--fixtures", nargs="+", default=list(FIXTURE_NAMES))
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--out", default=str(ROOT / "docs" / "eval-results.json"))
    parser.add_argument("--report", default=str(ROOT / "docs" / "EVAL-RESULTS.md"))
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(argv)
    if args.report_only:
        doc = finish(json.loads(Path(args.out).read_text(encoding="utf-8")))
    else:
        timeouts = Timeouts(connect=5, listing=10, first_byte=300, idle=120, total=600)
        backend = OllamaBackend(BackendConfig("ol", "ollama", args.url), Transport(timeouts), NUM_CTX, MAX_REPLY_TOKENS)
        fixtures = [f for f in all_fixtures() if f.name in args.fixtures]

        def show(cell):
            print(f"{cell['model']:14} {cell['variant']:18} {cell['fixture']:24} {cell['state']:7} "
                  f"{_code(cell)}", flush=True)
        doc = run_matrix(backend, args.models, args.variants, fixtures, args.out, show, resume=not args.no_resume)
    Path(args.report).write_text(render_report(doc), encoding="utf-8")
    print(f"winner: {doc.get('winner')}; results: {args.out}; report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
