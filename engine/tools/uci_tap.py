#!/usr/bin/env python3
"""Transparent UCI tap: log everything a GUI and an engine say to each other.

Point a GUI's engine path at this script (with the real engine as the argument) and the GUI
talks to the engine through it. Every line in both directions is written to a log file, so a
handshake that fails can be read instead of guessed at. The tap changes nothing: bytes are
forwarded exactly as they arrive, in both directions, and the engine's exit status is passed on.

    python engine/tools/uci_tap.py --engine /path/to/jqe --log run.jsonl

The argument list is what the GUI will use as the engine path and arguments; on Windows a GUI
usually passes the path alone, so put the real command line in --engine:

    --engine "C:\\Games\\engines\\jqe-windows-x64-avx2.exe" --log C:\\temp\\jqe-tap.jsonl

Each record is one JSON object per line:
    {"t": <seconds since start>, "dir": "gui>engine" | "engine>gui", "line": "..."}
and a final record carries the exit status. Standard input and output are the protocol; the
diagnostics go to standard error, which is safe because the GUI does not read it as UCI.

Options:
    --log PATH          where to write the JSONL log (default: uci-tap-<pid>.jsonl in this dir)
    --echo              also mirror the log to stderr as it is written
    --cwd PATH          working directory for the engine (default: the engine's own directory,
                        which is where Pikafish-style engines expect their net file)

Exit status: the engine's; 2 if the engine could not be started.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


class Log:
    def __init__(self, path: Path, echo: bool) -> None:
        self.path = path
        self.echo = echo
        self.lock = threading.Lock()
        self.t0 = time.monotonic()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fp = path.open("w", encoding="utf-8", buffering=1)

    def write(self, direction: str, line: str) -> None:
        row = {"t": round(time.monotonic() - self.t0, 6), "dir": direction, "line": line}
        with self.lock:
            self.fp.write(json.dumps(row) + "\n")
            if self.echo:
                print(f"{row['t']:10.3f} {direction:12s} {line}", file=sys.stderr, flush=True)

    def event(self, **fields: object) -> None:
        row = {"t": round(time.monotonic() - self.t0, 6), **fields}
        with self.lock:
            self.fp.write(json.dumps(row) + "\n")
            if self.echo:
                print(f"{row['t']:10.3f} {fields}", file=sys.stderr, flush=True)

    def close(self) -> None:
        with self.lock:
            try:
                self.fp.close()
            except Exception:
                pass


def pump_gui_to_engine(src, dst, log: Log) -> None:
    """Forward the GUI's commands; the GUI closing stdin is the normal shutdown signal.

    `quit` is forwarded like any other command and stdin stays open, so the engine can still
    finish writing its own reply (a GUI closes stdin right after quit anyway).
    """
    try:
        for raw in iter(src.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            log.write("gui>engine", text)
            dst.write(raw)
            dst.flush()
    except (BrokenPipeError, OSError, ValueError) as exc:
        log.event(event="gui_stdin_error", error=repr(exc))
    finally:
        log.event(event="gui_stdin_eof")
        try:
            dst.close()
        except Exception:
            pass


def pump_engine_to_gui(src, dst, log: Log) -> None:
    """Forward the engine's replies; an EOF here means the engine died or quit."""
    try:
        for raw in iter(src.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            log.write("engine>gui", text)
            dst.write(raw)
            dst.flush()
    except (BrokenPipeError, OSError, ValueError) as exc:
        log.event(event="engine_stdout_error", error=repr(exc))
    finally:
        log.event(event="engine_stdout_eof")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Log a UCI session between a GUI and an engine")
    ap.add_argument("--engine", required=True,
                    help="the real engine command line; may contain arguments")
    ap.add_argument("--log", type=Path,
                    default=Path(__file__).with_name(f"uci-tap-{os.getpid()}.jsonl"))
    ap.add_argument("--echo", action="store_true", help="mirror records to stderr")
    ap.add_argument("--cwd", type=Path, help="working directory for the engine")
    args, extra = ap.parse_known_args(argv)

    log = Log(args.log.expanduser().resolve(), args.echo)
    # A GUI often appends its own arguments to the configured path; keep them, in order.
    command = [args.engine] + [str(x) for x in extra]
    cwd = args.cwd.expanduser().resolve() if args.cwd else Path(args.engine).expanduser().resolve().parent
    log.event(event="start", command=command, cwd=str(cwd), log=str(log.path))

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                bufsize=0, creationflags=creationflags)
    except OSError as exc:
        log.event(event="spawn_failed", error=repr(exc))
        log.close()
        print(f"uci_tap: cannot start {command[0]}: {exc}", file=sys.stderr, flush=True)
        return 2
    log.event(event="spawned", pid=proc.pid)

    def pump_engine_stderr(src) -> None:
        for raw in iter(src.readline, b""):
            log.event(event="engine_stderr", line=raw.decode("utf-8", "replace").rstrip("\r\n"))

    threads = [
        threading.Thread(target=pump_gui_to_engine, args=(sys.stdin.buffer, proc.stdin, log),
                         daemon=True),
        threading.Thread(target=pump_engine_to_gui, args=(proc.stdout, sys.stdout.buffer, log),
                         daemon=True),
        threading.Thread(target=pump_engine_stderr, args=(proc.stderr,), daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    code = proc.wait()
    log.event(event="exit", returncode=code, returncode_hex=hex(code & 0xFFFFFFFF))
    log.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
