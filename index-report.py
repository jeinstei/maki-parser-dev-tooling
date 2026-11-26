#!/usr/bin/env python3
"""Summarise indexer metrics captured by index-stats.sh.

    index-report.py <dir> [<dir>...]

Reads <dir>/metrics.csv and prints savings by size bucket, by language, and an
overall line. Buckets are by *source* size, since that is what the agent would
otherwise have read in full.
"""

import csv
import sys
from pathlib import Path

BUCKETS = [
    ("< 2 KB", 0, 2_000),
    ("2-10 KB", 2_000, 10_000),
    ("10-50 KB", 10_000, 50_000),
    ("50-200 KB", 50_000, 200_000),
    (">= 200 KB", 200_000, None),
]

COLS = ("src_lines", "src_words", "src_bytes", "idx_lines", "idx_words", "idx_bytes")


def load(dirs):
    rows = []
    for d in dirs:
        p = Path(d) / "metrics.csv"
        if not p.exists():
            continue
        with p.open() as fh:
            for r in csv.DictReader(fh):
                r["corpus"] = Path(d).name
                for c in COLS:
                    r[c] = int(r[c] or 0)
                rows.append(r)
    return rows


def pct(before, after):
    return 100.0 * (1 - after / before) if before else 0.0


def bucket_rows(rows):
    out = []
    for label, lo, hi in BUCKETS:
        sel = [r for r in rows if r["src_bytes"] >= lo and (hi is None or r["src_bytes"] < hi)]
        if not sel:
            continue
        sb = sum(r["src_bytes"] for r in sel)
        ib = sum(r["idx_bytes"] for r in sel)
        sw = sum(r["src_words"] for r in sel)
        iw = sum(r["idx_words"] for r in sel)
        sl = sum(r["src_lines"] for r in sel)
        il = sum(r["idx_lines"] for r in sel)
        out.append((label, len(sel), sl, il, sw, iw, sb, ib))
    return out


def table(title, rows):
    print(f"\n## {title}\n")
    print("| Bucket | Files | Lines | → | Saved | Words | → | Saved | Bytes | → | Saved |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    tl = tli = tw = twi = tb = tbi = tn = 0
    for label, n, sl, il, sw, iw, sb, ib in rows:
        tn += n
        tl += sl; tli += il; tw += sw; twi += iw; tb += sb; tbi += ib
        print(
            f"| {label} | {n} | {sl} | {il} | {pct(sl, il):.1f}% "
            f"| {sw} | {iw} | {pct(sw, iw):.1f}% "
            f"| {sb} | {ib} | {pct(sb, ib):.1f}% |"
        )
    print(
        f"| **All** | **{tn}** | **{tl}** | **{tli}** | **{pct(tl, tli):.1f}%** "
        f"| **{tw}** | **{twi}** | **{pct(tw, twi):.1f}%** "
        f"| **{tb}** | **{tbi}** | **{pct(tb, tbi):.1f}%** |"
    )


def main(dirs):
    rows = load(dirs)
    if not rows:
        sys.exit("no metrics.csv found in " + ", ".join(dirs))

    ok = [r for r in rows if r["status"] == "ok"]
    bad = [r for r in rows if r["status"] == "error"]
    empty = [r for r in rows if r["status"] == "empty"]
    print(
        f"# Indexer savings\n\nFiles: {len(rows)} "
        f"({len(ok)} ok, {len(empty)} empty, {len(bad)} error)"
    )
    if empty:
        print(
            f"\n{len(empty)} file(s) indexed to nothing: no declarations to report "
            "(comment-only, or a directive such as `pragma). They are excluded from "
            "the savings tables, because a zero-byte index would flatter the ratio."
        )
    if bad:
        print(f"\nErrors: {len(bad)}")
        for r in bad[:10]:
            print(f"- {r['path']} ({r['status']})")

    table("All corpora, by source size", bucket_rows(ok))

    corpora = sorted({r["corpus"] for r in ok})
    if len(corpora) > 1:
        allrows = []
        for c in corpora:
            sel = [r for r in ok if r["corpus"] == c]
            allrows.append(
                (
                    c,
                    len(sel),
                    sum(r["src_lines"] for r in sel),
                    sum(r["idx_lines"] for r in sel),
                    sum(r["src_words"] for r in sel),
                    sum(r["idx_words"] for r in sel),
                    sum(r["src_bytes"] for r in sel),
                    sum(r["idx_bytes"] for r in sel),
                )
            )
        table("By corpus", allrows)

    for lang in sorted({r["lang"] for r in ok}):
        sel = [r for r in ok if r["lang"] == lang]
        table(f"Language: {lang}", bucket_rows(sel))


if __name__ == "__main__":
    main(sys.argv[1:] or ["."])
