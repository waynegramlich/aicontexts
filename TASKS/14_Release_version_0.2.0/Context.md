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
* 2026-11-20: release.yml 44826584339 (testpypi) failed in `build`:
  pylint R0913 too-many-arguments on `print_items()` (6/5), from
  `total` added by `--ordered` (da20849).  It also failed locally; the
  earlier "clean" check only tailed the output, and a single R message
  still rounds to 10.00.  Check pylint's exit status, not the score.
  Nothing was uploaded.  At the user's wish the code was fixed rather
  than quieted: `print_items()` was merged into its only caller,
  `Items.show()`, which takes `priority` and `prefix` from the
  collection (5 arguments with `self`); its tests moved to
  `_test_show()`, plus one for old numbers (634 checks).
* `release_check.py source` failed locally (all Pythons): it expected
  `Active_Rules.md` without the `GENERATED_COMMENT` line that `T.ssc`
  (42f7962) added.  Fixed; 3.11 to 3.15 all pass.
* release.yml 44828776193 (testpypi, adc3cc3): build passed with the
  newest linters; approved by Claude.  Superseded by #12's commit,
  which needs its own rehearsal before the tag.
* #12: `_test_interrupted_transfer()` now takes one `Transfer` tuple
  instead of four keyword arguments; no `too-many-arguments`
  suppressions remain in the code.
