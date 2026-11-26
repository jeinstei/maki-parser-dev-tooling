#!/usr/bin/env python3
"""Capture indexer metrics for many files, in parallel.

    index-stats.py <outdir> <jobs> <lang:file>...

Each file is one task, so a job slot is never idle waiting on a batch. The
harness keeps all state in-process, so tasks share nothing and run concurrently.

Writes <outdir>/out/<key>.index.txt (key = md5(path)[:16], so a deep path
cannot overflow the filename limit) for every file and <outdir>/metrics.csv
with the full `wc` triplet before and after.
"""

import csv
import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RUN = os.environ.get("RUN", str(Path(__file__).resolve().parent / "run.sh"))
COLS = ["path", "lang", "status", "src_lines", "src_words", "src_bytes",
        "idx_lines", "idx_words", "idx_bytes"]
ERROR_MARKERS = ("<NIL>", "lua error in index_dump", "stack traceback")


def wc(path):
    with open(path, "rb") as fh:
        data = fh.read()
    return data.count(b"\n"), len(data.split()), len(data)


def one(outdir, lang, path):
    key = hashlib.md5(path.encode()).hexdigest()[:16]
    out = outdir / "out" / (key + ".index.txt")
    try:
        res = subprocess.run(
            ["bash", RUN, path, lang], capture_output=True, text=True, errors="replace"
        )
        raw, status = res.stdout + res.stderr, ("ok" if res.returncode == 0 else "error")
    except OSError as e:
        raw, status = str(e), "error"
    if any(m in raw for m in ERROR_MARKERS):
        status = "error"
    elif not raw.strip():
        status = "empty"
    out.write_text(raw)
    sl, sw, sb = wc(path)
    il, iw, ib = wc(out)
    return [path, lang, status, sl, sw, sb, il, iw, ib]


def main(argv):
    outdir, jobs = Path(argv[0]), int(argv[1])
    probe = subprocess.run(["bash", RUN, "--check"], capture_output=True, text=True)
    if probe.returncode != 0:
        sys.exit(f"harness unavailable:\n{probe.stderr.strip()}")
    tasks = []
    for spec in argv[2:]:
        lang, _, path = spec.partition(":")
        tasks.append((outdir, lang, path))
    (outdir / "out").mkdir(parents=True, exist_ok=True)

    done = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool, (outdir / "metrics.csv").open(
        "w", newline=""
    ) as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for row in pool.map(lambda t: one(*t), tasks):
            w.writerow(row)
            done += 1
            if done % 200 == 0:
                print(f"{done}/{len(tasks)}", flush=True)
    print(f"done {done}/{len(tasks)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
