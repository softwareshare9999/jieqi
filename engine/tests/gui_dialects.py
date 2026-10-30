"""Replay the PengfeiChess handshake and game-start sequence against jqe through the tap.

This is the regression test for the reported failure: PengfeiChess sends a seven-field FEN
(board side pools captured - no-capture number). Before the fix jqe answered
"info string bad fen: bad no-capture count" and never produced a bestmove, so the GUI showed
a dead engine.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine" / "build" / "jqe.exe"
TAP = ROOT / "engine" / "tools" / "uci_tap.py"
NET = ROOT / "engine" / "nets" / "it014.jqn"

START = "xxxxkxxxx/9/1x5x1/x1x1x1x1x/9/9/X1X1X1X1X/1X5X1/9/XXXXKXXXX"

# The dialects a GUI may use for the same position.
FENS = {
    "jqe/pikafish 5-field": f"{START} w R2A2C2P5N2B2r2a2c2p5n2b2 0 1",
    "jieqibox 6-field": f"{START} w R2A2C2P5N2B2r2a2c2p5n2b2 - - 0 1",
    "jieqibox trailing": f"{START} w - - 0 1 R2A2C2P5N2B2r2a2c2p5n2b2",
    "pengfei 7-field": f"{START} w A2B2N2R2C2P5a2b2n2r2c2p5 - - 0 1",
    "pengfei 6-field": f"{START} w A2B2N2R2C2P5a2b2n2r2c2p5 - 0 1",
    "ace uci_pf": f"{START} $R2A2C2P5N2B2r2a2c2p5n2b2 w - - 0 1",
}


def run(fen: str, tmp: Path) -> tuple[list[str], list[dict]]:
    log = tmp / "tap.jsonl"
    commands = [
        "uci",
        "isready",
        f"setoption name EvalFile value {NET}",
        "ucinewgame",
        f"position fen {fen}",
        "go movetime 400",
        "quit",
    ]
    proc = subprocess.run(
        [sys.executable, str(TAP), "--engine", str(ENGINE), "--log", str(log)],
        input="".join(c + "\n" for c in commands), text=True,
        capture_output=True, timeout=120,
    )
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
    return proc.stdout.splitlines(), rows


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        for name, fen in FENS.items():
            stdout, rows = run(fen, tmp)
            replies = [r["line"] for r in rows if r.get("dir") == "engine>gui"]
            problems = []
            if not any(x == "uciok" for x in replies):
                problems.append("no uciok")
            if not any(x == "readyok" for x in replies):
                problems.append("no readyok")
            bad = [x for x in replies if "bad fen" in x or "bad move" in x]
            if bad:
                problems.append("engine rejected input: " + "; ".join(bad))
            if not any(x.startswith("bestmove ") and x != "bestmove (none)" for x in replies):
                problems.append("no usable bestmove")
            status = "ok" if not problems else "FAIL"
            best = next((x for x in replies if x.startswith("bestmove ")), "-")
            print(f"{status:4}  {name:22}  {best:16}  {'' if not problems else '; '.join(problems)}")
            failures += bool(problems)
    print(f"\n{len(FENS) - failures}/{len(FENS)} dialects accepted")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
