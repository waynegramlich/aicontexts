# 3 Generate the AI Contexts Rules file

Today each project copies `AI_Contexts_Rules.md` by hand and imports it
with `@AI_Contexts_Rules.md` in `CLAUDE.md`, so the copy goes stale when
`ai_contexts` changes, and `CLAUDE.md` depends on a file that may not
be there.

The rule: `CLAUDE.md` only points at content that is KNOWN to exist, so
processing `CLAUDE.md` never fails because of a missing file.

The design:

* The text of `AI_Contexts_Rules.md` lives inside `ai_contexts.py` (e.g.
  as a string constant).  This is the only way it works: there is no
  external file to install, find or keep in sync, and the rules always
  match the program that wrote them.
* Every time `ai_contexts` runs, it writes the file into every
  collection (`TASKS/`, `ISSUES/` and `RULES/`).  The duplication does
  not matter, since the file is small, and whichever collections a
  project has, the file is there.  It is generated (like `Startup.md`),
  so a copy edited by hand is put back; changes are made in
  `ai_contexts.py`.
* `CLAUDE.md` imports only one copy (e.g. `@TASKS/AI_Contexts_Rules.md`),
  since importing several would load the same rules more than once.
* Every run checks the `@` imports in `CLAUDE.md` and reports any whose
  file does not exist.
* The README's "Getting Started" and "Installation" sections drop the
  step of copying `AI_Contexts_Rules.md`, and the top-level
  `AI_Contexts_Rules.md` in this project goes away.
