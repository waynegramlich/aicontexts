# 10.3 Follow the Python Coding Rules

Bring `ai_contexts.py` and `ai_contexts_test.py` up to the Python Coding
Rules (`R.pcr`), one step at a time so that each can be committed:

1. Run `ruff format --line-length 79`.
2. Dataclasses (`slots=True`, explicit `field(...)`, grouped and
   alphabetized fields, a `Constructor:` section) and `Attributes:`
   sections for every class.
3. Function and method docstrings with `Arguments:`, `Returns:` and
   `Raises:` sections, and a docstring for every function.
4. Docstring and comment lines of 72 characters or fewer.
5. A `#` comment at the front of each block of code, and a type hint
   for every variable.
