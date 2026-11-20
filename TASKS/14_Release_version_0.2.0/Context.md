# LLM Agent Context Log

Release `aicontexts` 0.2.0 by the `R.gwr` Release Procedure (first
release since 0.1.0 on 2026-10-26, tag `v0.1.0` on e5e2541).

* 2026-11-20: `__version__` bumped to 0.2.0.  Before the bump: 633
  checks pass, ruff, ruff format, mypy --strict, pylint 10.00 and
  actionlint all clean; `uv` and `uv tool` tools current.
* Next: the user commits (with the RULES activation of `R.gsr` and
  `R.gwr`), Claude pushes, then rehearses `release.yml -f
  target=testpypi` (the first run of the unpinned lint tools on
  GitHub), then tag `v0.2.0` and `target=pypi` at the user's go.
* 2026-11-20: at the user's word, deactivated `R.gsr` and `R.gwr`
  (most users do not need them; `R.cmr` was already InActive).  The
  version stays 0.2.0, since nothing was tagged or uploaded.  A later
  session that does a release reads
  `rule_sources/GitHub_Workflow_Rules.md` (and `GitHub_Setup_Rules.md`)
  on demand.
