# Summary of `T.rv0` Release version 0.2.0

Released `aicontexts` 0.2.0 on pypi.org (2026-11-20; tag `v0.2.0` on
c3d500d).  `R.gsr` and `R.gwr` were deactivated (most users do not
need them); a release reads them from `rule_sources/`.  The first
rehearsal failed on pylint R0913 in `print_items()`, missed locally by
judging the score instead of the exit status; fixed by merging it into
`Items.show()`, and `_test_interrupted_transfer()` now takes one
`Transfer` tuple, so no `too-many-arguments` suppressions remain.
`release_check.py` was updated for `GENERATED_COMMENT` in
`Active_Rules.md` (broken since `T.ssc`).  Runs: release.yml
44829434482 (testpypi `0.2.0.dev202611202230`) and 44830073490 (pypi
0.2.0; two jobs re-run after the index lagged), all passed.
