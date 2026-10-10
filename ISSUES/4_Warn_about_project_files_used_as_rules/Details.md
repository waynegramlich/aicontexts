# 4 Warn about project files used as rules

Following the `README.md` rules recipe in `../alt_venv` with
`aic r create 1 ../claude_code_rules/*.md` also made rules from
`CLAUDE.md` and `README.md`, which are not rules.  The recipe now lists
the files by name, but `aic` should also catch this:

* Refuse to make a rule from a `CLAUDE.md` file.
* Ask (once per command) before using a file named in capital letters
  (e.g. `README.md`) or one with an `@` import, skipping them unless the
  answer is yes.
* Insist that every rule's source file ends in `.md`.
