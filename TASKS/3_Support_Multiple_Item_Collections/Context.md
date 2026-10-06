# LLM Agent Context Log

## Summary

A collection is any directory holding `.tracker.json`, found in the
current directory or the nearest parent that has any.  Commands are
`tracker COLLECTION COMMAND ...`; collection and command names take any
unique case-insensitive prefix, and an ambiguous one lists the options.
`tracker NAME create` makes a collection (name as typed, beside the others,
after a yes/no prompt).  `--help`/`--test` are options.  The one
`TASKS/Startup.md` covers every collection (e.g. `@../ISSUES/...`).

## 2026-10-05 Design discussion

Plan: support Tasks and Issues first.  Later, Rules and Skills:
* Rules (the user's term): Markdown files `@`-imported from `CLAUDE.md`,
  always loaded into context.  A Rules collection could use the item
  state to decide whether `Startup.md` imports the rule.
* Skills (Claude Code's term): a directory with a `SKILL.md` (frontmatter
  `name` + `description`), usually under `.claude/skills/`.  Only the
  description is loaded up front; the body is read on demand or via
  `/name`.  Both will probably be supported eventually.

Decisions:
1. Command form: `tracker COLLECTION COMMAND ARGUMENTS...`.  The
   collection is always required and is the first argument on every
   command (no hidden default, no reserved command words there).
2. Collection and command names may be truncated to any prefix, matched
   case-insensitively (`tracker i ...` -> `ISSUES/`, `tracker t cl 2` ->
   Tasks close 2).  An ambiguous prefix is an error that lists the
   matching options.
3. A collection is any directory containing a `.tracker.json` marker
   file.  It may later hold per-collection settings (e.g. each
   collection's own states and which states load `Context.md`).
4. Creating a collection: `tracker FULL_NAME create` (no number or
   title), after a yes/no prompt.
5. `tracker` searches upward from the current directory (like `git`) for
   the project's collections.
6. Still exactly one `TASKS/Startup.md`, covering every collection
   (e.g. `@../ISSUES/...`).
7. Switch-over: the existing `TASKS/` gets a `.tracker.json` once.

Further decisions:
* The marker file is `.tracker.json` (currently just `{}`).
* `tracker` alone, `-h` or `--help` prints help; `--test` runs the tests.
  Each collection also has a `help` command.
* A new collection is named exactly as typed.  It goes next to the
  existing collections if any are found up the tree, else in the current
  directory, and is always created after a yes/no prompt.  No extra
  typo protection; the prompt (which shows the full path) is enough.

## 2026-10-05 Implementation

* Module helpers: `matches(word, names)` (case-insensitive prefix match;
  an exact match wins), `find_collections(start)` (upward search),
  `write_startup(collections)` (moved out of `Items`; writes only if a
  `TASKS` collection exists, `STARTUP_COLLECTION`; TASKS items first,
  then the others; paths via `os.path.relpath`).
* `COMMANDS` maps command names to what they run (`ls` -> `list`), so
  an alias is not ambiguous with its command.
* `Items(directory)` has no default any more; it creates the directory
  and `.tracker.json` if missing (that is the "initialize" primitive).
* `Items.create_collection()` handles `NAME create`: rejects names with
  `/`, `.`, `..`, or an existing path; asks via the injectable `ask`
  (default `input`; EOF counts as no).
* `Items.run_command(arguments, ask=input)`.  Collections that fail to
  load (e.g. read-only) are skipped when writing `Startup.md`, so it is
  not truncated.
* `_test_commands` runs in its own temporary directory, because the
  upward search would otherwise find the other tests' collections.
* Switch-over done: `TASKS/.tracker.json` added.  157 checks pass.
* Not done: an `ISSUES` collection (`tracker ISSUES create`) is the
  user's call.

## 2026-10-05 Test coverage

coverage.py is not installed; the stdlib `trace` module is used:

```sh
python3 -m trace --count --missing --summary -C /tmp/cover \
    --ignore-dir=/usr/lib tracker.py --test
grep -n '>>>>>>' /tmp/cover/tracker.cover
```

Result: 159 checks, 99% of lines.  The only unexecuted lines are the
`# pragma: no cover` ones (a check failing, or running as root).  Two
gaps were found and closed with new tests: `set_state()` to the same
state, and `create_collection()` failing to write `Startup.md`.
`trace` measures lines, not branches.
