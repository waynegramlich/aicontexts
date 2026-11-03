# Summary of `T.ssc` Shrink the startup context

Startup context went from 66 KB to about 22 KB (2026-11-03).  The user
wants Claude to load only terse text Claude wrote for Claude.
`R.pcr` was rewritten tersely (12.6 KB to 2.5 KB); flake8 was dropped
for ruff `extend-select = ["B", "E", "W"]`, and `[tool.mypy]` adds
`warn_unreachable` and three error codes; workflow lint tools are no
longer pinned (`R.gwr` says so).  `RULES_TEXT` went from 7.4 KB to
1.3 KB: prompts and messages now say what to answer or do
(`AI_REPORTS`), generated files carry `GENERATED_COMMENT`, and syntax
is left to `-h`.  A closed child is in `Startup.md` only while its
parent is Reference (`SUMMARY_PARENT_STATES`).  `CLAUDE.md` no longer
imports `README.md`; it has Claude's own summary.  `REFERENCE.md` is
now Claude's design notes, read on demand through the path-scoped
`.claude/rules/ai_contexts_code.md`, which loads when
`ai_contexts.py` is touched; check next session that it does.  The
README now suggests `uv tool install --editable` for a local copy.
Not yet run on GitHub: the unpinned workflows.  The user is removing
flake8 from `ezpkg` and `solidcraft` themselves.
