# LLM Agent Context Log

## 2026-10-05 Planning discussion (complete)

Starting point: `tracker.py` was a straight copy of `claude_notes/task.py`
(the `task` program: Task/phrase/status/identifier, `.status` files,
`TASKS/Startup`).  The goal was to move it towards `README.md`.

Decisions (lettered as discussed):
* A. Each class of Item (issues, tasks, ...) is an independent collection
  in its own directory.  Became task 3, not a Cleanup step.
* B. New Items start in the `Pending` state.
  States: Pending, Open, Reference, Suspended, Closed.  `Reference` (the
  user suggested "Visible") means not being worked on, but `Context.md`
  is still imported by `Startup.md`.
* C. Number and Title stay in the directory name (`1.2.3_Cleaned_Title`)
  and the `Details.md` heading (`# 1.2.3 Title`).  Everything else lives
  in a hidden JSON file, `.item.json`, so fields (e.g. tags, which are
  planned) can be added easily.
* D. There is exactly one `TASKS/Startup.md`.  It contains only Claude
  Code `@` imports: `Details.md` for every Item, plus `Context.md` for
  Open and Reference Items.  It will cover every collection (e.g.
  `@../ISSUES/...`).
* E. No `tracker note` command; Claude edits `Context.md` directly.
  Timestamps go in `.item.json` in UTC (`2026-10-05T21:35:00Z`) and are
  shown in the local time zone by `tracker ls -l`.  Keep `created`,
  `updated`, and a timestamp for every state change ("history"); only
  the code reads the history, but it costs nothing to keep.
* F. `tracker` lives in this repository; `claude_notes/task.py` will
  eventually be deleted.  `../alt_venv` still uses `RULES/task.py` and
  `RULES/Task_Tracking_Rules.md`, so those are left alone for now; this
  repo has its own `Tracker_Rules.md`.
* Version control: Claude checkpoints into the `hg` repository here
  (created this session) without announcing it; the user commits to
  `git`.

Outcome: task 2 (Cleanup) and task 3 (Support Multiple Item
Collections).  See task 2's `Context.md` for what was implemented.
