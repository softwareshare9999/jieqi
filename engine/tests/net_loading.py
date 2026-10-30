"""Check that the net is found and loaded without any GUI telling the engine about it.

The engine also reports the state of the net, which is the only way to tell from inside a GUI
whether it is searching with NNUE or with the classical fallback.
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine" / "build" / "jqe.exe"
NET = ROOT / "engine" / "nets" / "it014.jqn"
START_BESTMOVE_WITH_NET = "a3a4"   # what it014 plays from the start position
START_BESTMOVE_CLASSICAL = "h2h6"


class Engine:
    def __init__(self, exe: Path, cwd: Path | None = None):
        self.p = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  cwd=str(cwd) if cwd else None, text=True, bufsize=1)
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.q.put(line.rstrip())
        self.q.put(None)

    def send(self, *lines):
        for line in lines:
            self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def until(self, pred, timeout=30):
        out, t0 = [], time.time()
        while time.time() - t0 < timeout:
            try:
                line = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            if line is None:
                break
            out.append(line)
            if pred(line):
                return out
        return out

    def isready(self):
        self.send("isready")
        return self.until(lambda l: l == "readyok")

    def bestmove(self, movetime=800):
        self.send("position startpos", f"go movetime {movetime}")
        lines = self.until(lambda l: l.startswith("bestmove"), timeout=60)
        best = next((l.split()[1] for l in lines if l.startswith("bestmove")), None)
        return best, lines

    def close(self):
        try:
            self.send("quit")
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def nnue_line(replies):
    return next((r for r in replies if r.startswith("info string nnue")), "(no nnue line)")


def main() -> int:
    if not ENGINE.is_file():
        print(f"missing engine: {ENGINE}")
        return 2
    if not NET.is_file():
        print(f"missing net: {NET}")
        return 2
    failures = 0

    def check(name, ok, detail):
        nonlocal failures
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:34} {detail}")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)

        # 1. No net anywhere near the executable: classical evaluation, and the engine says so.
        bare = tmp / "bare"
        bare.mkdir()
        shutil.copy2(ENGINE, bare / "jqe.exe")
        e = Engine(bare / "jqe.exe", cwd=bare)
        e.send("uci")
        e.until(lambda l: l == "uciok")
        replies = e.isready()
        best, infos = e.bestmove()
        e.close()
        check("no net on disk", "off (classical eval)" in nnue_line(replies), nnue_line(replies))
        check("info line flags nnue 0", any("nnue 0" in l for l in infos), "seen" if any("nnue 0" in l for l in infos) else "absent")

        # 2. Net beside the executable: found and loaded with no configuration at all.
        beside = tmp / "beside"
        beside.mkdir()
        shutil.copy2(ENGINE, beside / "jqe.exe")
        shutil.copy2(NET, beside / "it014.jqn")
        e = Engine(beside / "jqe.exe", cwd=beside)
        e.send("uci")
        e.until(lambda l: l == "uciok")
        replies = e.isready()
        best, infos = e.bestmove()
        e.close()
        check("net beside executable", "loaded" in nnue_line(replies), nnue_line(replies))
        check("info line flags nnue 1", any("nnue 1" in l for l in infos), "seen" if any("nnue 1" in l for l in infos) else "absent")
        check(f"start move is {START_BESTMOVE_WITH_NET}", best == START_BESTMOVE_WITH_NET, str(best))

        # 3. Net in nets/: also found.
        nested = tmp / "nested"
        (nested / "nets").mkdir(parents=True)
        shutil.copy2(ENGINE, nested / "jqe.exe")
        shutil.copy2(NET, nested / "nets" / "it014.jqn")
        e = Engine(nested / "jqe.exe", cwd=nested)
        e.send("uci")
        e.until(lambda l: l == "uciok")
        replies = e.isready()
        e.close()
        check("net in nets/", "loaded" in nnue_line(replies), nnue_line(replies))

        # 4. An explicit EvalFile overrides discovery; an empty one turns the net off.
        e = Engine(beside / "jqe.exe", cwd=tmp)  # cwd has no net, discovery still finds it beside the exe
        e.send("uci")
        e.until(lambda l: l == "uciok")
        e.send(f"setoption name EvalFile value {NET}")
        replies = e.isready()
        check("explicit EvalFile", "loaded" in nnue_line(replies), nnue_line(replies))
        e.send("setoption name EvalFile value")
        replies = e.isready()
        check("empty EvalFile turns it off", "off (classical eval)" in nnue_line(replies), nnue_line(replies))
        best, _ = e.bestmove()
        e.close()
        check(f"classical start move {START_BESTMOVE_CLASSICAL}", best == START_BESTMOVE_CLASSICAL, str(best))

        # 5. A file with the right name but the wrong content is not loaded.
        decoy = tmp / "decoy"
        decoy.mkdir()
        shutil.copy2(ENGINE, decoy / "jqe.exe")
        (decoy / "it014.jqn").write_bytes(b"not a net at all")
        e = Engine(decoy / "jqe.exe", cwd=decoy)
        e.send("uci")
        e.until(lambda l: l == "uciok")
        replies = e.isready()
        e.close()
        check("decoy file ignored", "off (classical eval)" in nnue_line(replies), nnue_line(replies))

    print(f"\n{'all checks passed' if not failures else str(failures) + ' failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
