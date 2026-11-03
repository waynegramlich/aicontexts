# aicontexts

<!--
Written by Claude, for Claude.  The user wants Claude to load only text
digested this way.  `README.md` is for people and is not imported;
`REFERENCE.md` is read on demand.
-->

* The `aicontexts` PyPI package: `ai_contexts.py`, one stdlib-only
  file (Python 3.11+) that manages the collections (`TASKS/`,
  `ISSUES/`, `RULES/`) whose files Claude loads at startup.  `aic` is
  a tracked symbolic link to it.  Version: `__version__`.
* Tests: `ai_contexts_test.py` (`./aic --test`); every change gets
  tests.  Try changing commands in a scratch directory.
* `README.md` is the user's manual; `REFERENCE.md` is Claude's design
  notes.  `.claude/rules/ai_contexts_code.md` says when to read them.
* `release_check.py` installs and tests as a stranger would;
  `.github/workflows/check.yml` and `release.yml` follow `R.gwr`
  (`rule_sources/GitHub_Workflow_Rules.md`).
* `rule_sources/` holds the rule source files, which other projects
  (e.g. `ezpkg`, `solidcraft`) also use.

@TASKS/AI_Contexts_Rules.md
@RULES/Active_Rules.md
@TASKS/Startup.md
