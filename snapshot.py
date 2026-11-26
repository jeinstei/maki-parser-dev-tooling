#!/usr/bin/env python3
"""Snapshot indexer output for many files, in parallel.

    snapshot.py <outdir> <jobs> [path...]

Same shape as index-stats.py: one task per file, a job slot is never idle
waiting on a batch, and the harness shares no state between tasks.

Files default to ./corpus plus any directory named in $CORPORA (space
separated). Writes one <outdir>/<key>.index.txt per file, keyed by path so two
snapshots of the same tree can be compared with `diff -r`.

Vivado-generated netlists account for most of the bytes in a real design tree --
ten 5-18 MB files are ~72% of the corpus -- and each costs ~14s on one core, so
they dominate wall time without testing anything the netlists beside them do not.
They are skipped above MAX_BYTES unless SNAPSHOT_ALL=1.
"""

import hashlib
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = os.environ.get("RUN", str(HERE / "run.sh"))
EXTS = {".vhd": "vhd", ".v": "v", ".sv": "sv", ".svh": "sv"}
ERROR_MARKERS = ("<NIL>", "lua error in index_dump", "stack traceback")
MAX_BYTES = 0 if os.environ.get("SNAPSHOT_ALL") else 5_000_000
PANIC_ID = re.compile(r"(thread '[^']*') \(\d+\)")
PANIC_FIX = r"\1"


def key(path):
    return hashlib.md5(path.encode()).hexdigest()[:16] + ".txt"


def one(outdir, path, lang):
    try:
        res = subprocess.run(
            ["bash", RUN, path, lang], capture_output=True, text=True, errors="replace"
        )
        raw = res.stdout + res.stderr
        status = "ok" if res.returncode == 0 else "error"
    except OSError as e:
        raw, status = str(e), "error"
    # A panic is reported with the thread id, which changes each run; drop it so a
    # real change in that file stays visible in a diff.
    raw = PANIC_ID.sub(PANIC_FIX, raw)
    if any(m in raw for m in ERROR_MARKERS):
        status = "error"
    elif not raw.strip():
        status = "empty"
    (outdir / key(path)).write_text(raw)
    return path, status


def default_files():
    roots = [HERE / "corpus"]
    roots += [Path(p) for p in os.environ.get("CORPORA", "").split()]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix in EXTS and path.is_file() and path.stat().st_size <= MAX_BYTES:
                yield str(path)


def main(argv):
    outdir, jobs = Path(argv[0]), int(argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    paths = argv[2:] or list(default_files())
    probe = subprocess.run(["bash", RUN, "--check"], capture_output=True, text=True)
    if probe.returncode != 0:
        sys.exit(f"harness unavailable:\n{probe.stderr.strip()}")
    tasks = [(outdir, p, EXTS[Path(p).suffix]) for p in paths]

    counts = {"ok": 0, "empty": 0, "error": 0}
    done = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for path, status in pool.map(lambda t: one(*t), tasks):
            counts[status] += 1
            done += 1
            if done % 200 == 0:
                print(f"{done}/{len(tasks)}", flush=True)
    print(f"done {done}/{len(tasks)} {counts}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
