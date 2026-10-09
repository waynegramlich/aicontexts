# LLM Agent Context Log

2026-10-09: Added `R.cmr` (Code Marker Rules, from
`../claude_code_rules/Code_Marker_Rules.md`) and activated it.  Added its
markers to `ai_contexts.py` (108) and `ai_contexts_test.py` (25) with an
`ast`-based script (top-level functions and classes, and their methods;
nested definitions are skipped, markers go above decorators).  `R.pcr`
is still InActive; not asked to activate it yet.
