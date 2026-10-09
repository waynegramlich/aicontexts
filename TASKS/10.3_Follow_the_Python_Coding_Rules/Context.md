# LLM Agent Context Log

Baseline (2026-10-09): 0 of 121 functions with arguments had an
`Arguments:` section; ~116 docstring/comment lines over 72 columns; no
class had `Attributes:`; `CollectionType` (frozen) and `Item` dataclasses
lack `slots=True` and `field(...)`; 21 functions (mostly nested test
helpers) had no docstring.
Step 1 done: `ruff format --line-length 79` (ruff.toml already sets 79);
`.flake8` now ignores E203, which conflicts with `ruff format` slices.
Step 2 done: `CollectionType` is `frozen=True, slots=True` and `Item` is
`slots=True`, with every field an explicit `field(init=True...)` under
`# Constructor arguments:` (all of their fields are constructor
arguments), and `Attributes:` and `Constructor:` docstring sections.
`Items` (a plain class with 5 attributes set in `__init__`) and
`RenumberInterrupted` have `Attributes:` sections.  `Item.priority`
stays `int | None`, since no priority is a real state.  The test file
has no classes.
Step 3 done: all 150 functions (109 in `ai_contexts.py`, 41 in the
tests, including nested helpers) have docstrings with `Arguments:`,
`Returns:` and `Raises:` sections (Raises lists exceptions that escape,
not ones caught inside).  Written by hand in batches and applied with an
`ast`-based script that rewraps each docstring to 72 columns; every new
docstring line is 72 or fewer, so step 4 is left with comments, the
module docstrings and anything else over 72.
