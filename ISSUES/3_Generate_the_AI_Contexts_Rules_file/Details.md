# 3 Generate the AI Contexts Rules file

Today each project copies `AI_Contexts_Rules.md` by hand and imports it
with `@AI_Contexts_Rules.md` in `CLAUDE.md`, so the copy goes stale when
`ai_contexts` changes.

Instead, `ai_contexts` should write `AI_Contexts_Rules.md` into the
collections itself (e.g. `TASKS/AI_Contexts_Rules.md`, beside
`TASKS/Startup.md`) every time it runs, so `CLAUDE.md` imports
`@TASKS/AI_Contexts_Rules.md` and the rules NEVER become stale: they
always match the program that is running.  The README's "Getting
Started" and "Installation" sections then drop the copy step.
