#!/bin/bash
# usage: run.sh <file> <lang-key>
#
# Indexes one file and prints the skeleton. The Lua driver is built on stdout
# and piped into index-dump, so concurrent invocations share no state and can
# run in parallel.
set -uo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bin=${INDEX_DUMP:-$here/index-dump/target/debug/index-dump}
if [ ! -x "$bin" ]; then
  echo "index-dump not built: run 'cargo build' in $here/index-dump" >&2
  exit 1
fi
[ "${1:-}" = "--check" ] && exit 0

# --kinds prints the node kinds the tree holds, one per line, instead of the
# index. It reads the same source as an index run, so an audit costs one extra
# invocation rather than a second parse of the file.
if [ "${1:-}" = "--kinds" ]; then
  f="$2"; lang="$3"
  case "$lang" in
    vhd) grammar=vhdl ;;
    sv | svh | v) grammar=systemverilog ;;
    *) grammar="$lang" ;;
  esac
  python3 - "$f" "$grammar" <<'PY' | "$bin" "$grammar" "$f" 2>&1
import sys

f, grammar = sys.argv[1], sys.argv[2]
src = open(f, encoding="utf-8").read()

level = 0
while True:
    close = "]" + "=" * level + "]"
    if close not in src:
        src = "[" + "=" * level + "[" + src + close
        break
    level += 1

print('local ts = maki.treesitter')
print('local p = assert(ts.get_parser(%s, %s))' % (src, repr(grammar)))
print('local seen = {}')
print('local function walk(n) seen[n:type()] = true for _, c in ipairs(n:named_children()) do walk(c) end end')
print('walk(p:parse()[1]:root())')
print('local k = {} for x in pairs(seen) do k[#k + 1] = x end table.sort(k)')
print('for _, x in ipairs(k) do print(x) end')
PY
  exit $?
fi

f="$1"; lang="$2"
python3 - "$f" "$lang" <<'PY' | "$bin" "$lang" "$f" 2>&1
import sys

f, lang = sys.argv[1], sys.argv[2]
src = open(f, encoding="utf-8").read()


def long_bracket(text):
    """A Luau long-bracket string at a depth the text cannot close early."""
    level = 0
    while True:
        close = "]" + "=" * level + "]"
        if close not in text:
            return "[" + "=" * level + "[" + text + close
        level += 1


print('local indexer = require("indexer")')
print('print((indexer.index_source(%s, indexer.EXT_TO_LANG[%s])) or "<NIL>")'
      % (long_bracket(src), repr(lang)))
PY
