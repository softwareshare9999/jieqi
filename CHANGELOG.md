# Changelog

## Unreleased

* **Engine.** Accept the FEN field orders that GUIs actually send, and diagnose the sessions that
  used to fail silently. PengfeiChess writes `board side pools captured - - no-capture number` and
  the ACE dialect writes `board $pools side - - no-capture number`; jqe read the fourth field as a
  counter, answered `info string bad fen: bad no-capture count`, kept the previous position and
  still replied with a plausible `bestmove` for that stale position. The pool, the side and the two
  counters are now recognised by shape, so every dialect above loads ([engine/README.md](engine/README.md),
  `engine/tests/gui_dialects.py`).
* **Diagnostics.** `JQE_LOG=PATH` (or `log PATH`) records the whole UCI dialogue, and
  `engine/tools/uci_tap.py` logs the same for any engine from outside it.
* **Nets are found, and their use is visible.** The engine loads `it014.jqn`/`jqe.jqn` from `nets/`
  beside the executable, beside the executable, or the working directory, taking only files with the
  `JQN1` magic; an explicit `EvalFile` overrides it and an empty one turns it off. `isready` reports
  `info string nnue loaded PATH` or `nnue off (classical eval)`, and every `info depth` line now
  carries `nnue 1` or `nnue 0` (`engine/tests/net_loading.py`).
* **Fixed.** The `EvalFile` option default was the placeholder `<empty>`. A GUI that writes its
  settings as XML — PengfeiChess does — produced a malformed `<Default><empty></Default>`, so its
  engine-options dialog hung on "loading" and never fetched the option list (jqe's stored
  `<Options />` was empty with `LastGetOptionsTime` at `01/01/0001`). The default is now an empty
  string.
* **GUI compatibility.** JieqiBox's old-order FEN for its human-versus-AI games carries no counters;
  it is accepted and read as `0 1`, as Pikafish and AB-JChess do. A `.jqn` path given as a
  command-line argument loads that net instead of being run as a one-shot command, so an engine
  started with its net as an argument still completes the UCI handshake. The README now lists which
  binary belongs in which GUI ([engine/README.md](engine/README.md)).

## 0.1.0 (2026-10-13)

The first release.

* **Engine.** jqe v0.15g, an alpha-beta engine with chance nodes for face-down movers and a UCI
  interface, in C++20 ([engine/README.md](engine/README.md)).
* **Net.** it014 (`engine/nets/it014.jqn`), the network the results were played with, and its
  training record ([results/training/](results/training/)).
* **Referee.** The rules library in `native/`, which decided every game, with its tests and the
  Python interface in `jieqi/` ([docs/NATIVE.md](docs/NATIVE.md), [RULES.md](RULES.md)).
* **Match harness.** Refereed matches in colour-swapped pairs on seeded deals
  (`engine/tools/match.py`, `formal.py`), the adapters for musesfish and universe-st Jieqi, and
  the recipes for the opponents ([THIRD_PARTY.md](THIRD_PARTY.md)).
* **Results.** The records of the formal runs, of a long-clock run against AB-JChess and of the
  exploiter test ([results/README.md](results/README.md)).
* **Checks.** `tools/check_results.py` recomputes every result from the records, and
  `tools/check_all.sh` builds and checks a clean clone ([CONTRIBUTING.md](CONTRIBUTING.md)).

The opponents, the AB-JChess net and the engine's training data are not in the repository.
THIRD_PARTY.md says where the opponents come from and how they were built.
