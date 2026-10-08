# Summary of `T.ehrc` Explore Having a Rules Collection

Collections now have a type in `.tracker.json` ("items", the default, or
"rules"; `tracker C type [TYPE]`, only while empty) that sets their states,
state commands, item files and what is loaded; this covers most of `I.pss`.
`RULES/` replaced the `RULES` symlink (Claude Code will not import through
it without approval): each rule is a read-only copy of a source file kept
relative to the project root (`tracker r create PLACE FILE...` with globs,
`source`), refreshed every run by SHA-256 (an edited copy is kept and
reported; `refresh` asks before replacing it; a missing source keeps the
copy).  Rules are Active or InActive; `RULES/Active_Rules.md` imports the
Active copies and `CLAUDE.md` imports it.  Every run reports a rule with no
source, an Active rule with no copy, an `@` import of a real file in a
copy, and a copy `CLAUDE.md` also imports.  `R.vcr` is Active; `R.pcr` is
InActive until it is rewritten.  Documented in `README.md`,
`Tracker_Rules.md` and `tracker -h`.
