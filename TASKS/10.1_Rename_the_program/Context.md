# LLM Agent Context Log

Scope survey (2026-10-09), before a name is chosen:
* Program: `tracker.py`, the `tracker` symlink, `tracker_test.py`.
* Docs: `README.md`, `Tracker_Rules.md` (imported by `CLAUDE.md`).
* Marker files `.tracker.json` (16 code references to them or to
  `TRACKER_*` test variables); used by this project and `../alt_venv`
  (`TASKS/`, `ISSUES/`), so a marker-name change needs a migration.
* Closed items' `.md` files mention `tracker` historically; leave them.
* The repository directory is `projects/tracker`.

Decision (2026-10-09): the program is `ai_contexts` (it manages a collection
of AI contexts; `ai_context` is probably blocked on PyPI by the existing
`aicontext`, and `ai_contexts`/`aicontexts` were free).  Done:
* `tracker.py`, `tracker_test.py`, the `tracker` symlink and
  `Tracker_Rules.md` became `ai_contexts.py`, `ai_contexts_test.py`,
  `ai_contexts` and `AI_Contexts_Rules.md`; `CLAUDE.md` imports the latter.
* `.tracker.json` became `.ai_contexts.json`; `find_collections()` renames
  an old one when it finds it (`OLD_COLLECTION_FILE`,
  `_test_old_collection_file`).  This project's collections are migrated.
* `TRACKER_TEST_*` became `AI_CONTEXTS_TEST_*`.
* `README.md` retitled "AI Contexts: Managing What Claude Code Loads".
* Closed items' text still says `tracker`; left as history.
Left for the user: renaming the directory `projects/tracker` to
`projects/ai_contexts`, and `../alt_venv`, whose `TRACKER -> ../tracker/`
and `tracker -> TRACKER/tracker` symlinks and `@TRACKER/Tracker_Rules.md`
import in `CLAUDE.md` need updating (its `.tracker.json` files migrate on
the first run).  No short `aic` symlink was added.
