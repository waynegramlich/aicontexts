# Summary of `T.c` Cleanup

Renamed Task/phrase/status/identifier to Item/title/state/number.  States:
Pending (new items), Open, Reference, Suspended, Closed; Open and Reference
items get their `Context.md` loaded.  `.status` became `.item.json` (state,
UTC `created`/`updated`, state `history`, later `tag` and `priority`); an old
`.status` is migrated on load.  `TASKS/Startup` became `TASKS/Startup.md`.
`README.md` was rewritten and `Tracker_Rules.md` added; `CLAUDE.md` imports
it instead of `RULES/Task_Tracking_Rules.md`, which `../alt_venv` still uses
with `RULES/task.py` (`claude_notes/task.py` will eventually be deleted).
