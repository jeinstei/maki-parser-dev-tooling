# maki-parser-dev-tooling

Development tooling for the maki `index` plugin. Lives outside the maki repo
because none of it ships: a harness binary, corpus runners, and report scripts.

## Layout

| Path | What it is |
|---|---|
| `index-dump/` | Cargo bin that loads the `index` plugin into a Lua host and runs an extractor over one file. Depends on `maki-lua` by path. |
| `run.sh` | Indexes one file; builds the Lua driver and pipes it into `index-dump`. |
| `snapshot.py` | Runs every file in a corpus in parallel and keys each output by its path, so two runs diff directly. Skips files over 5 MB (generated netlists) unless `SNAPSHOT_ALL=1`. |
| `index-stats.py` | Captures `wc` metrics for many files in parallel into a CSV, keeping every output. |
| `index-report.py` | Summarises a captured CSV by source-size bucket and by corpus. |
| `dropped.py` | Lists what a change stopped emitting, for checking nothing was lost. |

Corpora and captured statistics are **not** part of this repo. Point the scripts
at any tree you have locally.

## Verification runs

A real design tree is mostly generated netlist: in one 3,300-file HDL corpus, ten
files over 5 MB hold 72% of the bytes, and each costs about 14s on one core. They
are skipped by default, because they exercise nothing the files beside them do
not.

```sh
CORPORA="$HOME/git/corpus-a" python3 snapshot.py /tmp/after "$(nproc)"
# ~1,700 files in ~20s at 32 jobs; the same set with netlists included takes ~3min
```

Several corpora may be named at once, separated by spaces:

```sh
CORPORA="$HOME/git/corpus-a $HOME/git/corpus-b" python3 snapshot.py /tmp/after 24
```

Two snapshots of the same tree compare with `diff -r`. Capture the baseline from
the change reverted, then diff. A change that alters nothing shows zero
differences; anything else is attributable to the change under test.

## Setup

`index-dump` links against the working tree at `../maki`, so clone this next to
the maki checkout and build once:

```sh
cd index-dump && cargo build
```

The lockfile is pinned to the same dependency versions maki uses. A fresh
resolve picks up newer crates whose API has moved and fails to compile, so keep
`Cargo.lock`.

The plugin Lua is embedded in `maki-lua` via `include_dir!`, so **after editing
anything under `maki/plugins/index`** touch the loader and rebuild, or the
harness silently keeps running the old code:

```sh
touch ../maki/maki-lua/src/loader.rs && cargo build
```

A build that finishes without `Compiling maki-lua` is stale. This has produced
hours of false conclusions, including a "this code path is dead" result that was
purely an artefact of the old binary.

### Comparing against a fixed tree

`index-dump/Cargo.toml` points at `../maki-frozen`, a pinned copy of the maki
tree, rather than the working checkout. That keeps the harness able to index a
language the working branch does not carry, and stops a branch switch from
changing the measurements underneath you. Create it with:

```sh
mkdir -p ~/git/maki-frozen && git -C ~/git/maki archive <rev> \
  | tar -x -C ~/git/maki-frozen
```

Point the two `maki-*` paths in `index-dump/Cargo.toml` at whichever tree you
want measured.

## Usage

```sh
# one file, by extension
./run.sh path/to/file.vhd vhd

# capture a corpus (one task per file, run in parallel)
python3 index-stats.py stats/my-corpus 12 $(sed 's/^/vhd:/' files.txt)

# report on one or more captures
python3 index-report.py stats/my-corpus
```

`index-stats.py` writes `<outdir>/metrics.csv` plus every indexer output under
`<outdir>/out/`, so a report can be re-sliced without re-running anything.

Paths inside `metrics.csv` are recorded exactly as passed on the command line.

Language keys are `EXT_TO_LANG` extensions (`vhd`, `v`, `sv`, `rs`, `ts`), not
language names — passing a language name yields `<NIL>`. `<NIL>` means the
grammar was not found, not that the harness failed.

## Notes

- Files are processed as **individual tasks**. Batching several files per worker
  makes the run serial in practice, whatever the worker count.
- `run.sh` holds no state, so invocations are safe to run concurrently.
- Indexer output is never committed. Reproduce any file with
  `./run.sh <file> <lang>`, and diff two runs with `snapshot.py`.
- A few real-world files are not valid UTF-8 and fail before indexing; they are
  reported as `error` rather than silently skipped.
- Files that index to nothing (comment-only, or a lone `` `pragma ``) are marked
  `empty` and excluded from savings, since a zero-byte index would flatter the
  ratio.
- The corpus is read, never modified. Nothing here writes into the tree it
  measures.

## Measured results

These are from private corpora, so only the shapes are reproducible. They are
recorded because they justify the defaults above.

| Measure | Value |
|---|---|
| Corpus size | 3,341 files (3,280 ok, 57 empty, 4 error) |
| Bytes saved, all sizes | 80.5% |
| Bytes saved, files under 2 KB | 72.6% |
| Bytes saved, files over 200 KB | 91.3% |
| Largest ten files | 72% of corpus bytes, ~14s each |
| Cold harness build | ~45s |
| Snapshot, 1,700 files, 24 jobs | ~20s |
