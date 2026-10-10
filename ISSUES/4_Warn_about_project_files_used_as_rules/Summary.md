# Summary of `I.wapfuar` Warn about project files used as rules

Found by dogfooding in `../alt_venv`: the `README.md` rules recipe's
`../claude_code_rules/*.md` also matched `CLAUDE.md` and `README.md`.
The recipe now uses `[A-Z]*_Rules.md` (`REFERENCE.md` lists the three
files).  `screen_sources()` checks the files for `create` and `source`
before anything is created: `source_name_error()` refuses a name not
ending in `.md`, a hidden or `RESERVED_NAMES` name, and `CLAUDE.md` /
`CLAUDE.local.md` (`CLAUDE_NAMES`); `source_doubts()` flags a stem in
capital letters (`CAPITALS_PATTERN`, e.g. `README`) or an `@` import of
an existing file, and these are listed in one `[y/N]` question and
skipped unless the answer is yes.  The rules text tells Claude to answer
no unless the user asked for the file.  Documented in `README.md`,
`REFERENCE.md` and `-h`; tested in `_test_rule_doubts()`.
