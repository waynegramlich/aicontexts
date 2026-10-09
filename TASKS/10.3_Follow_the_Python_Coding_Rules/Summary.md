# Summary of `T.fpcr` Follow the Python Coding Rules

`ai_contexts.py` and `ai_contexts_test.py` now follow `R.pcr`: `ruff
format` (`.flake8` ignores E203), slotted dataclasses with explicit
`field(...)` and `Attributes:`/`Constructor:` sections, `Arguments:` /
`Returns:` / `Raises:` docstrings for all 150 functions, comments and
docstrings within 72 columns, and a type hint for every variable that can
take one (from `dmypy inspect`).  Block comments (295) were added to
`ai_contexts.py` only, since the user is excluding test suites from that
part of the rule.  Each step was a separate commit.
