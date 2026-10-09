# LLM Agent Context Log

Notes before starting (2026-10-09): `T.rp` renamed the program to
`ai_contexts` and lightly edited `README.md` (new title "AI Contexts:
Managing What Claude Code Loads", an opening paragraph on its purpose and
the old name, a note that `.tracker.json` is migrated, rewrapped
paragraphs).  The rest has not been reviewed.  `AI_Contexts_Rules.md`
says much of the same for Claude and may need matching changes.

Progress (2026-10-09): `README.md` was reworked into a user's manual
(Wayne: the reader should think "useful and not hard to use"): opening
with the three categories and the benefit, Getting Started (create
collections, `CLAUDE.md` lines, create/ls a task, tags, shortening,
hierarchical numbers), Context Files, a task's life, States, Moving
Things Around, Priorities, Other Conveniences, Rules Collections and
Installation.  The internals moved word for word to `REFERENCE.md`
(not imported by `CLAUDE.md`).  Wayne marks focus areas and requests
with HTML comments; Claude flags its own edits in those areas with
`<!-- WAYNE: reason -->`.  New issues: `I.ldsilt`, `I.gacrf`.  Still
to do: make `AI_Contexts_Rules.md` match, and decide whether
`CLAUDE.md` imports `REFERENCE.md`.
