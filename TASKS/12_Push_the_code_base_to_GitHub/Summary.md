# Summary of `T.pcbtg` Push the code base to GitHub

Published https://github.com/waynegramlich/aicontexts (public, HTTPS,
remote `github`, `git_hooks/` adding an `Assisted-by:` trailer) and
released `aicontexts` 0.1.0 on pypi.org (MIT-0).  Packaging:
`pyproject.toml` (commands `ai_contexts` and `aic`, version from
`__version__`), `release_check.py` (a stranger's install and test),
`.github/workflows/check.yml` (lint plus 4 OS x Python 3.11-3.15) and
`release.yml` (Trusted Publishing; `testpypi` from `main`, `pypi` from
admin-only `v*` tags, with required approval).  The first Windows and
macOS runs found read-only file, `\r\n`, path printing and sorting, and
macOS `/` glob bugs, all fixed and recorded in `R.gwr`.  Along the way:
`TAG~NUMBER` references, `aic r copy`, the rules layout (a rule's
directory holds only `Details.md`), `RULES` made a rules collection on
creation, `R.gar` added, `R.pcr` gained its Checkers section, and
`R.vcr` now lets Claude run every `git` command but `commit`.  Runs:
release.yml 40391568647 (testpypi `0.1.0.dev202610261959`) and
40399623382 (pypi 0.1.0, tag `v0.1.0` on e5e2541), all checks passed.
