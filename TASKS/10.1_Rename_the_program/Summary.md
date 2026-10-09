# Summary of `T.rp` Rename the program

The program `tracker` became `ai_contexts` (with an `aic` symlink), since
its main job is managing the AI contexts Claude Code loads; `ai_context`
is probably blocked on PyPI by the existing `aicontext`.  `tracker.py`,
`tracker_test.py` and `Tracker_Rules.md` became `ai_contexts.py`,
`ai_contexts_test.py` and `AI_Contexts_Rules.md`; `TRACKER_TEST_*` became
`AI_CONTEXTS_TEST_*`.  The marker `.tracker.json` became
`.ai_contexts.json`, and `find_collections()` renames an old one when it
finds it.  The project directory became `projects/ai_contexts`.  Closed
items still say `tracker`.  `../alt_venv` still links to `../tracker/` and
imports `Tracker_Rules.md`; the user will fix it.
