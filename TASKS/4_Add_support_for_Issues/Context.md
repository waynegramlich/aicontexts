# LLM Agent Context Log

## 2026-10-05 Tags and priorities

Source: `RULES/Issue_Tracking_Rules.md` ("Issue Tracking Program"), which
names an issue by its priority digit plus the first letter of each word
of its phrase.  The user dropped the priority from the name ("tag"); the
priority is stored in `.item.json` instead.

Decisions / behavior:
* Tag = first letter or digit of each word, lower case; punctuation
  dropped; a hyphenated word gives only its first letter; "a", "an",
  "of", "the" ignored (`TAG_IGNORED_WORDS`).  If every word is ignored,
  the first letter or digit of the title is used.
* Tags are unique per collection and stable: a clash gives the *new* item
  the lowest free number from 2 (`cde`, `cde2`, ...).  This differs from
  the rules file, where both become `cde1`/`cde2`; renaming an existing
  tag would break references to it.
* Every collection gets tags (TASKS too), stored as `"tag"` in
  `.item.json`.  Items without one get one on load (`add_missing_tags()`,
  which does not change `updated`).
* `rename` keeps the tag if the new title gives the same base tag,
  otherwise makes a new unique one.  Per the rules file, Claude must then
  update references to the old tag.
* Priority: `"priority": 0..3` in `.item.json`, optional.  Command
  `priority NUMBER LEVEL` (`-` removes it).  `p` is now ambiguous
  (pending, priority); use `pe` / `pr`.
* `ls` columns: number, state, priority (`-` if none), tag, [times],
  title.

Done: `ISSUES/` collection created (`echo y | ./tracker ISSUES create`).
192 checks; coverage still 99% with only `# pragma: no cover` lines
missed.

Possible next steps (not discussed yet): select items by tag instead of
number (e.g. `tracker i close dbzib`); sort `ls` by priority.

## 2026-10-05 Priority per collection

* Confirmed by the user: tags are never renumbered (`cde` stays, the next
  is `cde2`), because tags show up in commit messages and the like.
* Priority is a per-collection feature in `.tracker.json`
  (`{"priority": true}`), set by `enable FEATURE` / `disable FEATURE`
  (`FEATURES = ("priority",)`, prefixes allowed).  `Items.settings` holds
  the parsed `.tracker.json`; a bad one is a collection error.
* When enabled: `ls` sorts by priority (0..3, then none), then number,
  and every listing shows the priority column.  When disabled: no column,
  and `priority` is refused; stored priorities are kept.
* `d` is now ambiguous (delete, disable); use `del` / `di`.
* ISSUES has priority enabled; TASKS does not.  208 checks; coverage
  still only misses `# pragma: no cover` lines.
