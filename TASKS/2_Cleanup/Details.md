# 2 Cleanup

Bring `tracker.py` into alignment with `README.md`:

1. Pure rename: Task -> Item, phrase -> title, status -> state,
   `task.py` -> `tracker`.  No behavior change; tests still pass.
2. States: add `Pending`; new items are created `Pending`.
3. Item metadata: decide where Title/Number/State live (keep the
   `Details.md` heading + `.status`, or a single metadata file), with
   migration of existing directories if the format changes.
4. Item classes: moved to task 3.
5. `Startup.md`: rename from `Startup`, and settle its location and
   contents.
6. Timestamps: `created` and `updated` (UTC) in `.item.json`, shown in
   the local time zone by `tracker ls -l`.
7. Documentation: fix `README.md` (typos included) and update the
   rules files.
