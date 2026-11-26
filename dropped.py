#!/usr/bin/env python3
"""Report declaration kinds a file's tree holds but its index never mentions.

    dropped.py [path...]

An extractor that has no arm for a node emits nothing for it, so the content is
silently missing from the skeleton. This looks for that: it reads the parse tree
through `run.sh --kinds`, reads the index through `run.sh`, and prints any
declaration kind that is present in the tree but has no marker in the output.

Only kinds that a declaration-shaped node would render are checked, because a
tree is mostly expressions and literals that no index should name. The markers
are the words the extractors print for that kind, so a kind spelled differently
is reported rather than missed.

A hit is a lead, not a verdict: a kind can be present and legitimately absent
when the construct it belongs to is deliberately unnamed (an unlabelled process,
a bare `assign`). Read the file before treating one as a bug.

Exit status is 1 when anything is reported, so a corpus sweep can gate on it.
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = os.environ.get("RUN", str(HERE / "run.sh"))
BIN = os.environ.get("INDEX_DUMP", str(HERE / "index-dump/target/debug/index-dump"))
EXTS = {".vhd": "vhd", ".v": "v", ".sv": "sv", ".svh": "sv"}
MAX_BYTES = 0 if os.environ.get("SNAPSHOT_ALL") else int(os.environ.get("MAX_BYTES", 200_000))
PROGRESS_EVERY = 100
TRUNCATED = "more truncated]"

# kind -> the words an index prints for it. An empty tuple means the kind is
# checked by presence alone, which is what a wrapper or an unnamed declaration
# looks like.
MARKERS = {
    "systemverilog": {
        # `localparam` contains `param`, and a net's type is arbitrary (`tri1`,
        # `uwire`, `supply0`, a user type), so the words are matched loosely.
        "parameter_declaration": ("param",),
        "local_parameter_declaration": ("param",),
        "class_declaration": ("class ",),
        "modport_declaration": ("modport ",),
        "function_declaration": ("(",),
        "task_declaration": ("(",),
    },
    "vhdl": {
        "constant_declaration": ("constant ",),
        "signal_declaration": (":",),
        "component_declaration": ("component ",),
        "entity_declaration": ("entity ",),
        "architecture_definition": ("architecture ",),
        "package_declaration": ("package ",),
        "package_definition": ("package body ",),
    },
}


def long_bracket(text):
    """A Luau long-bracket string at a depth the text cannot close early."""
    level = 0
    while "]" + "=" * level + "]" in text:
        level += 1
    return "[" + "=" * level + "[" + text + "]" + "=" * level + "]"


# The drivers below are what run.sh builds; they run here so a sweep costs one
# interpreter startup per file instead of one per invocation. `run.sh` spawns
# python3 three times per file, and startup alone is ~190 ms.
# Each kind is reported as `kind<TAB>parent`, with an empty parent for a node
# seen only at the root level. A declaration is only meaningful where the index
# is expected to name it, so the caller drops the kinds whose every occurrence is
# nested in a subprogram body: a function-local constant is implementation
# detail, not something a skeleton should list.
KINDS_DRIVER = """local ts = maki.treesitter
local p = assert(ts.get_parser(%s, %s))
local seen = {}
local function walk(n, parent)
  local k = n:type()
  if not seen[k] or seen[k] == "" then seen[k] = parent end
  for _, c in ipairs(n:named_children()) do walk(c, k) end
end
walk(p:parse()[1]:root(), "")
local k = {} for x in pairs(seen) do k[#k + 1] = x end
table.sort(k)
for _, x in ipairs(k) do print(x .. "\\t" .. seen[x]) end
"""

INDEX_DRIVER = """local indexer = require("indexer")
print((indexer.index_source(%s, indexer.EXT_TO_LANG[%s])) or "<NIL>")
"""


def run(lua, path, lang):
    res = subprocess.run([BIN, lang, path], input=lua, capture_output=True, text=True, errors="replace")
    return res.stdout if res.returncode == 0 else ""


# A declaration inside one of these is local to the subprogram, so the skeleton
# is right not to name it.
SUBPROGRAM_BODY = {
    "vhdl": {"subprogram_head"},
    "systemverilog": {"function_body_declaration", "task_body_declaration"},
}


def check(path, lang):
    grammar = "vhdl" if lang == "vhd" else "systemverilog"
    with open(path, encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    quoted = long_bracket(src)
    parents = {}
    for line in run(KINDS_DRIVER % (quoted, repr(grammar)), path, grammar).splitlines():
        kind, _, parent = line.partition("\t")
        if kind:
            parents.setdefault(kind, set()).add(parent)
    out = run(INDEX_DRIVER % (quoted, repr(lang)), path, lang)
    if not parents or not out.strip():
        return []
    # A marker is only evidence of a missing arm when nothing was cut. Where the
    # index reports a truncation, the kind may simply be past a section's budget,
    # and calling that a dropped declaration would bury the real hits.
    if TRUNCATED in out:
        return []
    local = SUBPROGRAM_BODY[grammar]
    table = MARKERS[grammar]
    return [
        kind
        for kind, words in table.items()
        if kind in parents
        and not parents[kind] <= local
        and words
        and not any(w in out for w in words)
    ]


def default_files():
    for p in os.environ.get("CORPORA", "").split():
        root = Path(p)
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix in EXTS and path.is_file() and path.stat().st_size <= MAX_BYTES:
                yield str(path)


def main(argv):
    paths = argv or list(default_files())
    tasks = [(p, EXTS[Path(p).suffix]) for p in paths]
    hits = done = 0
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 8) as pool:
        for path, dropped in pool.map(lambda t: (t[0], check(*t)), tasks):
            done += 1
            if dropped:
                hits += 1
                print(f"{path}: {', '.join(dropped)}")
            # Progress goes to stderr so a redirected stdout stays a clean list.
            # A newline per report, not a carriage return: a redirected stderr is
            # read back with a pager, where one unterminated line reads as silence.
            if done % PROGRESS_EVERY == 0 or done == len(tasks):
                print(f"{done}/{len(tasks)}", file=sys.stderr, flush=True)
    print(f"{hits}/{len(tasks)} file(s) with a declaration kind absent from the index")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
