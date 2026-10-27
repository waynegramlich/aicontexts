#!/usr/bin/env python3
"""Manage the AI contexts that Claude Code loads, in Markdown files.

The contexts are items (tasks, issues, rules and so on) kept in
collection directories.  Each run writes `TASKS/Startup.md` and
`RULES/Active_Rules.md`, whose `@` imports load the right files at the
start of each Claude Code session, and `AI_Contexts_Rules.md` (from
`RULES_TEXT`) into every collection (see `README.md` and `HELP`).
"""

# `pylint`'s size limits are turned off for this module: every variable
# has a type hint (which `pylint` counts as a local), and the program is
# a single file by design.
# pylint: disable=too-many-lines,too-many-locals,too-many-statements
# pylint: disable=too-many-return-statements,too-many-branches
# pylint: disable=too-many-instance-attributes,too-many-public-methods

import contextlib
import glob
import hashlib
import json
import os
import re
import shutil
import stat
import string
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

HELP: str = """Usage: ai_contexts COLLECTION COMMAND [ARGUMENTS...]
       ai_contexts TAG COMMAND [ARGUMENTS...]
                               Same as `ai_contexts COLLECTION COMMAND TAG ...`
                               for the collection of TAG (e.g. I.dbzib)
       ai_contexts NAME create Create the collection directory NAME (a rules
                               collection if NAME is RULES, in any case)
       ai_contexts --test      Run the self tests in a temporary directory
       ai_contexts -h | --help Print this help message
       ai_contexts --version   Print the version (e.g. aicontexts 0.1.0)
       ai_contexts             List the collections, one line each

A COLLECTION is a directory containing a `.ai_contexts.json` file.  They
are found in the current directory, or else the nearest parent directory
that has any, stopping at a version control root (a directory with .git
or .hg).  COLLECTION and COMMAND may be shortened to any unique
prefix, in any case (e.g. `ai_contexts t cl 2` closes item 2 in TASKS).
A new collection is created, after asking, next to the existing ones (or
else in the current directory) and is named exactly as typed.

Commands:
  create PLACE TITLE...   Create an item at PLACE (see below)
  create PLACE FILE...    In a rules collection, create a rule from each
                          FILE (or glob pattern), at PLACE and after.
                          Each FILE must end in .md, and a CLAUDE.md
                          file is refused; asks before using
                          a file that does not look like a rule (named
                          like README.md, or with an @ import)
  move NUMBER PLACE       Move an item, with its children, to PLACE.
                          NUMBER may be a range of siblings, like 1.2.5-6
  transfer NUMBER COLLECTION [PLACE]
                          Move an item, with its children, to PLACE in
                          another collection of the same type (by default
                          its next free top-level number); its tag gets
                          the new prefix.  NUMBER may be a range
  rename NUMBER to TITLE...
                          Change the title of an item
  delete [-r] NUMBER      Delete an item and all of its files; with -r,
                          after asking, its children too.  NUMBER may be
                          a range of siblings, like 1.2.5-6
  list [-a] [-l] [NUMBER] List the items, or NUMBER and its children,
                          except Closed ones (unless named, or -a)
  show NUMBER             Show everything about an item
  ls [-a] [-l] [NUMBER]   Same as list
  pending [-r] NUMBER     Set the item state to Pending (for this and the
                          other state commands, NUMBER may be a range of
                          siblings, like 1.2.5-6)
  open [-r] NUMBER        Set the item state to Open
  reference [-r] NUMBER   Set the item state to Reference
  suspend [-r] NUMBER     Set the item state to Suspended
  close [-r] NUMBER       Set the item state to Closed
  reject [-r] NUMBER      Set the item state to Rejected
  activate [-r] NUMBER    Set the rule state to Active (rules collections)
  deactivate [-r] NUMBER  Set the rule state to InActive (rules collections)
  source NUMBER FILE      Make FILE the source of a rule, and copy it
                          (checked like create)
  refresh NUMBER          Copy a rule's source over its copy, asking first
                          if the copy was edited in place
  copy DIRECTORY [CHOICES...]
                          List the rules in DIRECTORY (another project's
                          rules collection, or a directory of rule files)
                          by number and title, and copy the chosen ones
                          (e.g. 1,3-5 or 1 3-5; asked for if not given)
                          after the last rule, InActive, with their files
                          as their sources
  priority NUMBER LEVEL   Set the item priority: 0 (catastrophic), 1 (high),
                          2 (medium), 3 (low), or - for none
  enable FEATURE          Enable a collection feature (only: priority)
  disable FEATURE         Disable a collection feature
  type [TYPE]             Print the collection type, or set it to TYPE
                          (items or rules) while the collection is empty
  help                    Print this help message

Options:
  -r, --recursive         Also apply to all of the child items
  -a, --all               Also list the Closed and Rejected items
  -l, --long              Also list the created and updated times

Items are numbered without gaps: if 1.3 exists, so do 1.1 and 1.2.  A
PLACE is one of:
  NUMBER          The next free number of a level (e.g. 1.3 after 1.2, or
                  2.1.1 for the first child of 2.1)
  before NUMBER   Where item NUMBER is; it and its later siblings move
                  down one
  after NUMBER    Just after item NUMBER; its later siblings move down one
Deleting or moving items moves the later siblings (and their children) up
to close the gap.  There is no undo.  Before a move, rename or transfer,
if the last one in the collection was more than an hour ago, ai_contexts
recommends taking a version control snapshot (e.g. `git commit`) first,
and asks whether to continue.

Each collection has a type, kept in its `.ai_contexts.json`, which
decides its states, the files of its items and what Startup.md imports.
A new collection is an "items" collection.

The states of an "items" collection are: Pending, Open, Reference,
Suspended, Closed, Rejected.  New items are created Pending.  Open items
are being worked on.  Reference items are not, but like Open items their
Context.md is in Startup.md.  Closed items are done; Rejected items were
decided against, and are otherwise treated like Closed ones.  Each item
also has a Summary.md, written before it is closed or rejected.  For the
50 most recently closed or rejected items, Startup.md has their
Summary.md (or Details.md if the summary is empty); older ones are listed
by tag and title in a generated TASKS/Closed.md.

The states of a "rules" collection are Active and InActive (new rules are
InActive), set with `activate` and `deactivate`.  A rule has a Details.md
but no Context.md or Summary.md, and rules are not in Startup.md.  Each
rule has a source file, kept relative to the directory that holds the
collections, and its Details.md is a read-only copy of it.  Every
run copies a changed source again, unless the copy was edited in place,
and writes RULES/Active_Rules.md, which imports the copies of the Active
rules; add `@RULES/Active_Rules.md` to CLAUDE.md.  A rule must stand
alone: an `@` import of a file in a copy is reported, as is a copy that
CLAUDE.md also imports.

Each item has a tag: the capitalized first letter of its collection and a
period, then the first letter of each word of its title in lower case,
ignoring "a", "an", "of" and "the" (e.g. "Division by Zero is Bad" in
ISSUES is `I.dbzib`).  When a tag is already used in the collection, the
new item gets the lowest free number added (e.g. `I.cde2`).  Collections
must start with different letters.  A tag (with or without its prefix,
in any case) may be used wherever an item NUMBER is expected.  Text
refers to an item as its tag, `~` and its number when the text was
written (e.g. `I.dbzib~3`); the `~NUMBER` is accepted and ignored, since
it is never updated.

When priority is enabled for a collection, its items are listed by
priority first (0 to 3, then none) and the priority is shown.

Every run also writes AI_Contexts_Rules.md, which tells the AI how to use
ai_contexts, into every collection; add one of them (e.g.
`@TASKS/AI_Contexts_Rules.md`) to CLAUDE.md.  An `@` import in CLAUDE.md
whose file does not exist is reported."""

# The file that every run writes into every collection, with the rules
# for using ai_contexts that the AI loads (from `RULES_TEXT`).
RULES_FILE: str = "AI_Contexts_Rules.md"

# The contents of `RULES_FILE`.  It is kept here, not in a separate
# file, so that it always matches the program and needs nothing else
# installed.
RULES_TEXT: str = """# AI Contexts Rules

`ai_contexts` writes this file into every collection each time it runs,
so it always matches the program.  Never edit it; a change to it is
made in `ai_contexts.py`.

The `ai_contexts` program (often installed as `aic`) creates and manages
items in collections such as `TASKS/` and `ISSUES/`.  `ai_contexts` with
no arguments lists the collections, and `ai_contexts -h` lists all of
the commands.  Every command starts with the collection, which (like the
command) may be any unique prefix in any case.  The `create` command
(e.g. `ai_contexts TASKS create 1.2.3 New Task`, or `ai_contexts t cr
1.2.3 New Task`) creates an item directory (e.g. `TASKS/1.2.3_New_Task/`)
containing:

* `Details.md`:
  Edited by the human to describe the item.  Claude only edits it when
  asked to.
* `Context.md`:
  Edited by Claude to retain useful item context across sessions.
  Claude edits it directly; there is no `ai_contexts` command for it.
* `Summary.md`:
  Written by Claude before the item is closed (see below).
* `.item.json`:
  Managed by `ai_contexts`.  Claude changes the state with the
  `pending`, `open`, `reference`, `suspend`, `close` and `reject`
  commands (e.g. `ai_contexts t close T.fbm`), never by editing this
  file.

Each item has a tag (e.g. `I.dbzib` for "Division by Zero is Bad" in
`ISSUES/`), shown by `ai_contexts t ls`; `ai_contexts I.dbzib show`
shows everything about it.  To refer to an item in Markdown text and
commit messages, use its tag followed by `~` and its current number, in
back quotes (e.g. `I.dbzib~3`), so that its directory
(`ISSUES/3_Division_by_Zero_is_Bad/`) is easy to find.  Never use the
number alone.  Numbers change when items are created, deleted, moved or
transferred, and a `~NUMBER` is never updated: it records the number
when it was written, and the tag is what names the item.  Commands
accept a tag (in any case, but never shortened, and with or without a
`~NUMBER`, which is ignored) wherever they take a number, and a tag can
stand in for its collection (`ai_contexts T.fbm close`).  Renaming an
item can change its tag; `ai_contexts` then lists the `.md` files that
use the old tag and offers to update them, and Claude answers yes (after
checking the list) so that every reference changes in the same pass.

Every `ai_contexts` command checks its collections and prints what it
fixed and what needs fixing.  When it reports a problem, Claude fixes it
(usually with the `rename` command it suggests) or tells the user about
it.

Item numbers never have gaps.  `create` and `move` take a place: the
next free number of a level (e.g. `1.3`), or `before NUMBER` / `after
NUMBER` (e.g. `ai_contexts t move T.fbm after 2.1`, or `ai_contexts t
create before 1.1 Fix Big Mistake`).  `rename NUMBER to TITLE...`
changes a title.  There is no undo: when `ai_contexts` recommends a
version control snapshot before a move, rename or transfer and asks
whether to continue, Claude answers no, takes a snapshot (following the
project's version control rules), and then runs the command again.
`delete` is permanent: it refuses an item with children unless given
`-r` (which asks first), and renumbers the later items.  Never run
`delete` (or other changing commands) on the real items just to see what
happens; try it in a scratch directory.

An item that belongs in another collection of the same type (e.g. a
Task that turns out to be an Issue) is moved there, with its children,
by `ai_contexts t transfer T.fbm issues [PLACE]`.  Its tag gets the new
prefix (`T.fbm` becomes `I.fbm`), and `ai_contexts` offers to update the
`.md` files that use the old tags; as for a rename, Claude answers yes
after checking the list.  The update drops an old tag's `~NUMBER`
(`T.fbm~12` becomes `I.fbm`), since that number was in the other
collection.  Old tags are not looked up afterwards, so text must use the
new ones.

When priority is enabled for a collection (e.g. `ai_contexts i enable
priority`), items may have a priority set with `ai_contexts i priority
NUMBER LEVEL`, and `ls` lists them by priority first:

* **0**: A catastrophic bug that must be avoided at all costs, such as a
  security hole or a defect that escapes to where nobody can fix it.
* **1**: A high priority that needs to be fixed quickly.
* **2**: A medium priority that needs to be fixed next.
* **3**: A low priority that gets put near the end of the list.

`-` removes the priority.

New items start out Pending.  The states (of an "items" collection, like
`TASKS/` and `ISSUES/`) are Pending, Open, Reference, Suspended, Closed
and Rejected.  A Reference item is not being worked on, but its
`Context.md` is still loaded, so its context stays available.  A
Rejected item was decided against (`ai_contexts i reject NUMBER`); it is
treated like a Closed one, and its `Summary.md` says why.

Before closing an item, Claude writes its `Summary.md` (below the
heading line that `ai_contexts` maintains): what was decided and done,
with the tags (and `~NUMBER`s) of related items.  Once the item is
closed, only that summary is loaded at startup (and after the 50 most
recently closed, only its tag and title, in the generated
`TASKS/Closed.md`), so it should be enough to know that the item exists
and what it settled.
`ai_contexts T.fbm show` and the item's files give the rest when needed.

Every time `ai_contexts` is successfully run, it rewrites these files,
which Claude never edits:

* `TASKS/Startup.md`: `@` imports of the `Details.md` of every item that
  is not closed, the `Context.md` of every Open or Reference item and
  the `Summary.md` of the most recently closed items, in every
  collection.
* `TASKS/Closed.md`: the tags and titles of the older closed items.
* `RULES/Active_Rules.md`: `@` imports of the Active rules.
* `AI_Contexts_Rules.md` (this file), in every collection.

`CLAUDE.md` imports only files that are known to exist, such as these:

```
@TASKS/AI_Contexts_Rules.md
@TASKS/Startup.md
@RULES/Active_Rules.md
```

Every run reports an `@` import in `CLAUDE.md` whose file does not
exist; Claude tells the user about it.

`RULES/` is a rules collection (`ai_contexts r type` prints a
collection's type).  Each rule's `Details.md` is a read-only copy of a
source file elsewhere (e.g. `../shared_rules/Version_Control_Rules.md`),
made and refreshed by `ai_contexts`; its states are Active and InActive
(`ai_contexts r activate R.vcr`, `ai_contexts r deactivate R.vcr`).
Claude never edits a rule's copy: a change to a rule is made in its
source (and only when asked), and the next `ai_contexts` run copies it.
New rules come from files with `ai_contexts r create PLACE FILE...`,
or from another project's rules (or a directory of rule files) with
`ai_contexts r copy DIRECTORY [CHOICES...]`, which lists them by number
and title and copies the chosen ones (e.g. `1,3-5`); Claude gives the
CHOICES on the command line, as the user asked.  `ai_contexts r source
R.vcr FILE` changes a rule's source.  All three insist on a file ending
in `.md`, refuse a `CLAUDE.md` file, and ask before using a file that
does not look like a rule (one named in capital letters, like
`README.md`, or one with an `@` import); Claude answers no unless the
user asked for that file.  When `ai_contexts`
reports a copy edited in place, a missing source, an `@` import in a
rule or a rule that `CLAUDE.md` also imports, Claude tells the user
rather than fixing it with `refresh`.
"""

STATES: tuple[str, ...] = (
    "Pending",
    "Open",
    "Reference",
    "Suspended",
    "Closed",
    "Rejected",
)

# The states of finished items, which `ls` leaves out and `Startup.md`
# only summarizes.
FINISHED_STATES: tuple[str, ...] = ("Closed", "Rejected")

# The states whose `Context.md` is imported by `Startup.md`.
CONTEXT_STATES: tuple[str, ...] = ("Open", "Reference")

# The states of the items in a rules collection.
RULE_STATES: tuple[str, ...] = ("Active", "InActive")


# Class `CollectionType`:
@dataclass(frozen=True, slots=True)
class CollectionType:
    """How the items of one type of collection behave.

    Attributes:
    * `states` (`tuple[str, ...]`): The item states.
    * `new_state` (`str`): The state of a new item.
    * `finished_states` (`tuple[str, ...]`): The states that `ls` leaves
      out and `Startup.md` only summarizes.
    * `context_states` (`tuple[str, ...]`): The states whose
      `Context.md` is in `Startup.md`.
    * `state_commands` (`dict[str, str]`): The state that each state
      command sets.
    * `commands` (`tuple[str, ...]`): The type's other commands.
    * `files` (`tuple[str, ...]`): The Markdown files of each item.
    * `in_startup` (`bool`): True if `Startup.md` imports the files.
    * `has_sources` (`bool`): True if each item's `Details.md` is a
      copy of a source file (see `Items.check_rules()`), and its title
      is kept in `.item.json`.

    Constructor:
    * `CollectionType(states, new_state, finished_states,
      context_states, state_commands, commands, files, in_startup,
      has_sources)`
    """

    # Constructor arguments:
    states: tuple[str, ...] = field(init=True)
    new_state: str = field(init=True)
    finished_states: tuple[str, ...] = field(init=True)
    context_states: tuple[str, ...] = field(init=True)
    state_commands: dict[str, str] = field(init=True)
    commands: tuple[str, ...] = field(init=True)
    files: tuple[str, ...] = field(init=True)
    in_startup: bool = field(init=True)
    has_sources: bool = field(init=True)


# The types of collection, by the name kept in `.ai_contexts.json`.  A
# collection without a type is an "items" collection.
TYPES: dict[str, CollectionType] = {
    "items": CollectionType(
        states=STATES,
        new_state="Pending",
        finished_states=FINISHED_STATES,
        context_states=CONTEXT_STATES,
        state_commands={
            "pending": "Pending",
            "open": "Open",
            "reference": "Reference",
            "suspend": "Suspended",
            "close": "Closed",
            "reject": "Rejected",
        },
        commands=(),
        files=("Details.md", "Context.md", "Summary.md"),
        in_startup=True,
        has_sources=False,
    ),
    "rules": CollectionType(
        states=RULE_STATES,
        new_state="InActive",
        finished_states=(),
        context_states=(),
        state_commands={"activate": "Active", "deactivate": "InActive"},
        commands=("source", "refresh", "copy"),
        files=("Details.md",),
        in_startup=False,
        has_sources=True,
    ),
}
DEFAULT_TYPE: str = "items"

# The states of every type of collection.
ALL_STATES: tuple[str, ...] = tuple(
    dict.fromkeys(
        state
        for collection_type in TYPES.values()
        for state in collection_type.states
    )
)

# The state commands of every type of collection.
STATE_COMMANDS: dict[str, str] = {
    command: state
    for collection_type in TYPES.values()
    for command, state in collection_type.state_commands.items()
}

# The other commands of every type of collection.
TYPE_COMMANDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        command
        for collection_type in TYPES.values()
        for command in collection_type.commands
    )
)

# The file in each collection with sources (see `CollectionType`) that
# imports the copies of its Active items.
ACTIVE_RULES: str = "Active_Rules.md"

# The hidden file that a new copy of a source is written to before it
# replaces the old copy.
COPY_TEMPORARY: str = ".copy.tmp"

# The file names that a source file can not have, since its copy goes
# into an item directory.
RESERVED_NAMES: frozenset[str] = frozenset(
    {"Details.md", "Context.md", "Summary.md"}
)

# The file names (in lower case) that Claude Code loads by itself, so
# they can never be the source of a rule.
CLAUDE_NAMES: frozenset[str] = frozenset({"claude.md", "claude.local.md"})

# A file name stem in capital letters (e.g. `README`), which marks a
# file about the project rather than a rule.
CAPITALS_PATTERN: re.Pattern[str] = re.compile(r"[A-Z0-9_]*[A-Z][A-Z0-9_]*")

# An `@` import in Markdown: an `@` that starts a word, and the path
# after.
IMPORT_PATTERN: re.Pattern[str] = re.compile(r"(?<!\S)@(\S+)")

# The characters that make an argument a glob pattern.
GLOB_CHARACTERS: str = "*?["

# The hidden JSON file in each item directory that holds its metadata.
ITEM_FILE: str = ".item.json"

# The hidden file that held the state of an item in the old format.
OLD_STATUS_FILE: str = ".status"

# The hidden JSON file that marks a directory as a collection of items.
COLLECTION_FILE: str = ".ai_contexts.json"

# The hidden JSON file that marked a collection when the program was
# called `tracker`; it is renamed to `COLLECTION_FILE` when found.
OLD_COLLECTION_FILE: str = ".tracker.json"

# The version of ai_contexts itself (the format of its collections is
# `FORMAT_VERSION`).
__version__: str = "0.1.0"

# The version of the format of the collections, kept in
# `.ai_contexts.json`.
FORMAT_VERSION: str = "0.1"

# The hidden JSON file that holds a renumbering while it is being done,
# so that an interrupted renumbering can be finished.
RENUMBER_FILE: str = ".renumber.json"

# The environment variable with which the test suite interrupts a
# renumbering after that many steps.
INTERRUPT_VARIABLE: str = "AI_CONTEXTS_TEST_RENUMBER_INTERRUPT"

# The commands whose first argument is an item, so that `ai_contexts TAG
# COMMAND ...` can be used.
TAG_COMMANDS: frozenset[str] = frozenset(
    {
        "rename",
        "delete",
        "list",
        "show",
        "priority",
        "move",
        "transfer",
        *STATE_COMMANDS,
        *TYPE_COMMANDS,
    }
)

# The number of most recently closed items whose `Summary.md` is in
# `Startup.md`;
# the test suite can change it with the environment variable named by
# `SUMMARIES_VARIABLE`.
CLOSED_SUMMARIES: int = 50
SUMMARIES_VARIABLE: str = "AI_CONTEXTS_TEST_CLOSED_SUMMARIES"

# The hidden JSON file that holds a transfer of items to another
# collection while it is being done, so that an interrupted transfer can
# be finished.
TRANSFER_FILE: str = ".transfer.json"

# The keys of each item in `.transfer.json`.
TRANSFER_KEYS: tuple[str, ...] = (
    "old",
    "temporary",
    "new",
    "old_number",
    "new_number",
    "tag",
    "old_tag",
    "new_tag",
    "title",
    "summary",
)

# The keys of each rename in `.renumber.json`.
RENAME_KEYS: tuple[str, ...] = (
    "old",
    "temporary",
    "new",
    "old_number",
    "new_number",
)

# The entries that mark a version control root, where the search for
# collections stops.
VERSION_CONTROL_NAMES: tuple[str, ...] = (".git", ".hg")

# The collection that holds `Startup.md` for all of the collections.
STARTUP_COLLECTION: str = "TASKS"

# The priority levels, from catastrophic (0) to low (3).
PRIORITIES: tuple[int, ...] = (0, 1, 2, 3)

# The seconds after a move or rename before the next one reminds the
# user to take a version control snapshot.  The test suite can change it
# with the environment variable named by `DELAY_VARIABLE`.
MOVE_RENAME_DELAY_SECONDS: float = 3600.0
DELAY_VARIABLE: str = "AI_CONTEXTS_TEST_MOVE_RENAME_DELAY_SECONDS"

# The places relative to an existing item.
PLACES: tuple[str, ...] = ("before", "after")

# A stand-in name for an item that is about to be created.
NEW_ITEM: tuple[int, ...] = (0,)

# The features that can be enabled for a collection in
# `.ai_contexts.json`.
FEATURES: tuple[str, ...] = ("priority",)

# The words that are left out of a tag.
TAG_IGNORED_WORDS: frozenset[str] = frozenset({"a", "an", "of", "the"})

# The commands of every type of collection, and the command that each
# one runs; each type adds its state commands (see `commands()`).
COMMANDS: dict[str, str] = {
    "create": "create",
    "rename": "rename",
    "delete": "delete",
    "list": "list",
    "ls": "list",
    "priority": "priority",
    "move": "move",
    "transfer": "transfer",
    "show": "show",
    "enable": "enable",
    "disable": "disable",
    "type": "type",
    "help": "help",
}


# Class `RenumberInterrupted`:
class RenumberInterrupted(Exception):
    """A renumbering interrupted by the test suite.

    It is raised after the number of steps in the `INTERRUPT_VARIABLE`
    environment variable.

    Attributes:
    * None beyond those of `Exception`.
    """


# Function `read_file()`:
def read_file(path: Path) -> str:
    """Return the contents of a UTF-8 text file.

    Arguments:
    * `path` (`Path`):
      The file to read.

    Returns:
    * (`str`): The contents of the file.

    Raises:
    * `OSError`: If the file can not be read.
    """
    return path.read_text(encoding="utf-8")


# Function `write_file()`:
def write_file(path: Path, text: str) -> None:
    """Write a UTF-8 text file.

    Arguments:
    * `path` (`Path`):
      The file to write.
    * `text` (`str`):
      The new contents of the file.

    Raises:
    * `OSError`: If the file can not be written.
    """
    path.write_text(text, encoding="utf-8", newline="\n")


# Function `make_writable()`:
def make_writable(path: Path) -> None:
    """Make a file writable by its owner, if it exists.

    Windows can not replace or delete a read-only file (such as the copy
    of a rule's source), so one is made writable first.

    Arguments:
    * `path` (`Path`):
      The file.

    Raises:
    * `OSError`: If its mode can not be changed.
    """
    if path.is_file() and not path.is_symlink():
        path.chmod(path.stat().st_mode | stat.S_IWUSR)


# Function `remove_file()`:
def remove_file(path: Path) -> None:
    """Remove a file, even a read-only one, if it exists.

    Arguments:
    * `path` (`Path`):
      The file.

    Raises:
    * `OSError`: If it can not be removed.
    """
    make_writable(path)
    path.unlink(missing_ok=True)


# Function `remove_tree()`:
def remove_tree(directory: Path) -> None:
    """Remove a directory and everything in it, even read-only files.

    Arguments:
    * `directory` (`Path`):
      The directory.

    Raises:
    * `OSError`: If it can not be removed.
    """
    path: Path
    for path in directory.rglob("*"):
        make_writable(path)
    shutil.rmtree(directory)


# Function `new_metadata()`:
def new_metadata(state: str, stamp: str) -> dict[str, object]:
    """Return the metadata of a new item.

    The "history" list records every state change with its time.

    Arguments:
    * `state` (`str`):
      The state of the new item.
    * `stamp` (`str`):
      The UTC timestamp of its creation.

    Returns:
    * (`dict[str, object]`): The metadata for its `.item.json`.
    """
    return {
        "state": state,
        "created": stamp,
        "updated": stamp,
        "history": [{"state": state, "time": stamp}],
    }


# Function `write_item()`:
def write_item(item_directory: Path, metadata: dict[str, object]) -> None:
    """Write the metadata of an item into its `.item.json`.

    Arguments:
    * `item_directory` (`Path`):
      The item's directory.
    * `metadata` (`dict[str, object]`):
      The metadata to write.

    Raises:
    * `OSError`: If `.item.json` can not be written.
    """
    # Write the metadata as indented JSON.
    text: str = json.dumps(metadata, indent=2)
    write_file(item_directory / ITEM_FILE, f"{text}\n")


# Function `utc_stamp()`:
def utc_stamp(seconds: float) -> str:
    """Return a time as a UTC timestamp string.

    The timestamp is ISO 8601, like "2026-10-05T21:35:00Z".

    Arguments:
    * `seconds` (`float`):
      The time, in seconds since the epoch.

    Returns:
    * (`str`): The UTC timestamp.
    """
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Function `local_time()`:
def local_time(stamp: str) -> str:
    """Return a UTC timestamp in the local time zone.

    Arguments:
    * `stamp` (`str`):
      The UTC timestamp, which may be empty.

    Returns:
    * (`str`): The local time, "-" if `stamp` is empty, or "?" if it is
      not a valid timestamp with a time zone.
    """
    # An empty timestamp has no local time.
    if not stamp:
        return "-"

    # Parse the timestamp, which must have a time zone.
    try:
        moment: datetime = datetime.fromisoformat(stamp)
    except ValueError:
        return "?"
    if moment.tzinfo is None:
        return "?"
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


# Function `read_item()`:
def read_item(item_directory: Path) -> dict[str, object]:
    """Return the metadata in the `.item.json` of an item.

    An item directory in the old format, with a `.status` file instead,
    is migrated first, using the time of the `.status` file as the
    created and updated times.

    Arguments:
    * `item_directory` (`Path`):
      The item's directory.

    Returns:
    * (`dict[str, object]`): The item's metadata.

    Raises:
    * `OSError`: If a file can not be read or written.
    * `ValueError`: If `.item.json` is not a JSON object.
    """
    # Migrate an old `.status` file to `.item.json` first.
    item_path: Path = item_directory / ITEM_FILE
    old_path: Path = item_directory / OLD_STATUS_FILE
    if not item_path.exists() and old_path.is_file():
        write_item(
            item_directory,
            new_metadata(
                read_file(old_path).strip(),
                utc_stamp(old_path.stat().st_mtime),
            ),
        )
        old_path.unlink()

    # Read the metadata, which must be a JSON object.
    metadata: object = json.loads(read_file(item_path))
    if isinstance(metadata, dict):
        return metadata
    raise ValueError(f"'{item_path}' is not a JSON object")


# Function `update_item()`:
def update_item(
    item_directory: Path,
    state: str = "",
    fields: dict[str, object] | None = None,
) -> str:
    """Set the updated time in the `.item.json` of an item to now.

    Any other metadata is kept.

    Arguments:
    * `item_directory` (`Path`):
      The item's directory.
    * `state` (`str`):
      The new state, which is also appended to the "history" list, or
      "" to leave the state alone.
    * `fields` (`dict[str, object] | None`):
      Other fields to set; a field set to `None` is removed.

    Returns:
    * (`str`): The new updated time.

    Raises:
    * `OSError`: If `.item.json` can not be read or written.
    * `ValueError`: If `.item.json` is not a JSON object.
    """
    # Read the metadata and set its updated time.
    metadata: dict[str, object] = read_item(item_directory)
    stamp: str = utc_stamp(time.time())
    metadata["updated"] = stamp

    # Set or remove the other fields.
    key: str
    value: object
    for key, value in (fields or {}).items():
        if value is None:
            metadata.pop(key, None)
        else:
            metadata[key] = value

    # Change the state and record the change in the history.
    if state:
        history: object = metadata.get("history")
        if not isinstance(history, list):
            history = []
        history.append({"state": state, "time": stamp})
        metadata["state"] = state
        metadata["history"] = history

    # Write the metadata back.
    write_item(item_directory, metadata)
    return stamp


# Function `matches()`:
def matches(word: str, names: Iterable[str]) -> list[str]:
    """Return the names that a word abbreviates, ignoring case.

    A name equal to `word` (ignoring case) is the only match.  Otherwise
    every name that starts with `word` matches.

    Arguments:
    * `word` (`str`):
      The word, which may be an abbreviation.
    * `names` (`Iterable[str]`):
      The names to match.

    Returns:
    * (`list[str]`): The matching names, in the order of `names`.
    """
    # An exact match is the only match.
    folded: str = word.casefold()
    exact: list[str] = [name for name in names if name.casefold() == folded]
    if exact:
        return exact

    # Otherwise every name that starts with `word` matches.
    return [name for name in names if name.casefold().startswith(folded)]


# Function `collections_in()`:
def collections_in(directory: Path) -> list[Path]:
    """Return the collections directly in a directory.

    A collection is a sub-directory (not a symbolic link) holding a
    `.ai_contexts.json` (or an old `.tracker.json`) file.  An entry that
    can not be checked is skipped: on macOS, `/` has entries (such as
    `/.resolve`) that some Pythons can not even `stat`.

    Arguments:
    * `directory` (`Path`):
      The directory to look in.

    Returns:
    * (`list[Path]`): The collections, sorted.
    """
    # List the directory, which may not be readable.
    try:
        children: list[Path] = list(directory.iterdir())
    except OSError:
        return []

    # Keep each sub-directory that has a collection file.
    found: set[Path] = set()
    child: Path
    for child in children:
        file_name: str
        for file_name in (COLLECTION_FILE, OLD_COLLECTION_FILE):
            try:
                if (child / file_name).is_file() and not child.is_symlink():
                    found.add(child)
            except OSError:
                continue
    return sorted(found, key=Path.as_posix)


# Function `find_collections()`:
def find_collections(start: Path) -> list[Path]:
    """Return the collection directories nearest to a directory.

    `start` and then each of its parents is searched for
    sub-directories that contain a `.ai_contexts.json` file, stopping
    at the first directory that has any.  The search also stops after a
    version control root (a directory with `.git` or `.hg`), so that it
    never finds the collections of an enclosing project; without one,
    it goes all the way to `/`.  A collection that is a symbolic link
    is skipped.  A collection in the old format, with a `.tracker.json`
    file instead, is migrated by renaming that file.

    Arguments:
    * `start` (`Path`):
      The directory to start searching from.

    Returns:
    * (`list[Path]`): The collections in the first directory that has
      any, sorted, or an empty list if none are found.
    """
    # Search `start` and then each of its parents for collections.
    directory: Path
    for directory in (start, *start.parents):
        found: list[Path] = collections_in(directory)

        # Migrate any old `.tracker.json` files.
        path: Path
        for path in found:
            old_path: Path = path / OLD_COLLECTION_FILE
            if old_path.is_file() and not (path / COLLECTION_FILE).exists():
                try:
                    old_path.rename(path / COLLECTION_FILE)
                except OSError as error:
                    print(
                        f"Can not rename '{old_path}' to "
                        f"'{COLLECTION_FILE}': {error}",
                        file=sys.stderr,
                    )

        # Stop at the first directory that has collections, or after a
        # version control root.
        if found:
            return found
        if any((directory / name).exists() for name in VERSION_CONTROL_NAMES):
            break

    # No collections were found.
    return []


# Function `type_name()`:
def type_name(directory: Path) -> str:
    """Return the type of a collection, from its `.ai_contexts.json`.

    Arguments:
    * `directory` (`Path`):
      The collection's directory.

    Returns:
    * (`str`): The type, or `DEFAULT_TYPE` if the file can not be read
      or has no type.  An unknown type is returned as it is (`Items`
      reports it).
    """
    # Read the settings, if they can be read.
    try:
        settings: object = json.loads(read_file(directory / COLLECTION_FILE))
    except (OSError, ValueError):
        return DEFAULT_TYPE

    # The type is in the settings, if they are a JSON object.
    if isinstance(settings, dict):
        return str(settings.get("type", DEFAULT_TYPE))
    return DEFAULT_TYPE


# Function `commands()`:
def commands(name: str = "") -> dict[str, str]:
    """Return the commands of a collection type, or of every type.

    Arguments:
    * `name` (`str`):
      The name of the collection type, or "" for every type.

    Returns:
    * (`dict[str, str]`): Each command, mapped to the command that it
      runs.
    """
    # Add the commands of the type, or of every type.
    type_commands: Iterable[str] = (
        [*TYPES[name].state_commands, *TYPES[name].commands]
        if name in TYPES
        else [*STATE_COMMANDS, *TYPE_COMMANDS]
    )
    return {**COMMANDS, **{command: command for command in type_commands}}


# Function `other_type_error()`:
def other_type_error(word: str, name: str, directory: Path | None) -> str:
    """Return an error for a command of another type of collection.

    Arguments:
    * `word` (`str`):
      The command, as typed (any unique prefix).
    * `name` (`str`):
      The collection's name, as it was matched.
    * `directory` (`Path | None`):
      The collection's directory, or None if there is no one
      collection.

    Returns:
    * (`str`): The error, naming the type whose command it is and how to
      change the collection's type, or "" if `word` is not a command of
      exactly one other type.
    """
    # Find the one type, other than the collection's, with the command.
    if directory is None:
        return ""
    current: str = type_name(directory)
    found: list[tuple[str, str]] = sorted(
        {
            (kind, command)
            for kind, collection_type in TYPES.items()
            if kind != current
            for command in matches(
                word,
                [*collection_type.state_commands, *collection_type.commands],
            )
            if command not in commands(current)
        }
    )
    if len(found) != 1:
        return ""

    # Say whose command it is, and how to change the type.
    other: str
    command: str
    other, command = found[0]
    return (
        f"'{command}' is a command of {other} collections, and "
        f"{directory.name} is {article(current)} {current} "
        f"collection; while it has no items, `ai_contexts {name} type "
        f"{other}` makes it {article(other)} {other} collection"
    )


# Function `article()`:
def article(word: str) -> str:
    """Return "an" for a word starting with a vowel, or else "a".

    Arguments:
    * `word` (`str`):
      The word.

    Returns:
    * (`str`): The indefinite article.
    """
    return "an" if word[:1].casefold() in "aeiou" else "a"


# Function `sha256_of()`:
def sha256_of(path: Path) -> str:
    """Return the SHA-256 of a file.

    Arguments:
    * `path` (`Path`):
      The file.

    Returns:
    * (`str`): The SHA-256, in hexadecimal.

    Raises:
    * `OSError`: If the file can not be read.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Function `markdown_imports()`:
def markdown_imports(text: str) -> list[tuple[int, str]]:
    """Return each `@` import in Markdown text.

    Imports in fenced code blocks and in code spans are left out, since
    Claude Code does not follow them.

    Arguments:
    * `text` (`str`):
      The Markdown text.

    Returns:
    * (`list[tuple[int, str]]`): The line number and path of each
      import.
    """
    # Scan the lines, skipping fenced code blocks.
    found: list[tuple[int, str]] = []
    fence: str = ""
    number: int
    line: str
    for number, line in enumerate(text.splitlines(), 1):
        stripped: str = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            continue
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            continue

        # Find the imports outside of code spans.
        found += [
            (number, path)
            for path in IMPORT_PATTERN.findall(re.sub(r"`[^`]*`", "", line))
        ]

    # Return every import found.
    return found


# Function `expand_files()`:
def expand_files(arguments: list[str]) -> list[Path] | str:
    """Return the files named by arguments, expanding glob patterns.

    An argument with any of `GLOB_CHARACTERS` is a pattern, which must
    match at least one file; its matches are sorted.

    Arguments:
    * `arguments` (`list[str]`):
      The file names and patterns.

    Returns:
    * (`list[Path] | str`): The files, or an error string if an argument
      is not a file or a pattern matches nothing.
    """
    # Expand each pattern, which must match at least one file.
    files: list[Path] = []
    argument: str
    for argument in arguments:
        if any(character in argument for character in GLOB_CHARACTERS):
            matched: list[str] = sorted(glob.glob(argument))
            if not matched:
                return f"No files match '{argument}'"
            files += [Path(path) for path in matched]
        else:
            files.append(Path(argument))

    # Every file must exist.
    path: Path
    for path in files:
        if not path.is_file():
            return f"'{path.as_posix()}' is not a file"
    return files


# Function `is_rule_copy()`:
def is_rule_copy(path: Path) -> bool:
    """Return True if a file is a rule's `Details.md` in a rules collection.

    Arguments:
    * `path` (`Path`):
      The file.

    Returns:
    * (`bool`): True if `path` is `Details.md` in an item directory of a
      collection whose items are copies of sources.
    """
    collection: Path = path.parent.parent
    return (
        path.name == "Details.md"
        and TYPES.get(type_name(collection), TYPES[DEFAULT_TYPE]).has_sources
    )


# Function `rule_title()`:
def rule_title(path: Path, fallback: str) -> str:
    """Return the title of a rule file, from its first line.

    Arguments:
    * `path` (`Path`):
      The rule file.
    * `fallback` (`str`):
      The title to use when the first line is not a `# ` heading (or
      the file can not be read).

    Returns:
    * (`str`): The title.
    """
    try:
        heading: str = read_file(path).partition("\n")[0]
    except (OSError, ValueError):
        return fallback
    title: str = heading[2:].strip() if heading.startswith("# ") else ""
    return title or fallback


# Function `offered_rules()`:
def offered_rules(directory: Path) -> list[tuple[str, Path]]:
    """Return the rules in a directory that `copy` can copy.

    In a rules collection, they are the items' `Details.md` files, in
    number order; the collection is only read, never loaded, so nothing
    in it changes.  In any other directory, they are its `.md` files
    that can be sources (see `source_name_error()`), in name order.
    Each title is the file's first-line heading, or else (for an item)
    the title in its `.item.json`, or else the name.

    Arguments:
    * `directory` (`Path`):
      The directory.

    Returns:
    * (`list[tuple[str, Path]]`): The title and file of each rule.
    """
    # A plain directory offers its Markdown files.
    offered: list[tuple[str, Path]] = []
    if not TYPES.get(type_name(directory), TYPES[DEFAULT_TYPE]).has_sources:
        path: Path
        for path in sorted(directory.glob("*.md"), key=Path.as_posix):
            if path.is_file() and not source_name_error(path):
                offered.append(
                    (rule_title(path, path.stem.replace("_", " ")), path)
                )
        return offered

    # A rules collection offers its items' copies, in number order.
    numbered: list[tuple[tuple[int, ...], Path]] = []
    item_directory: Path
    for item_directory in directory.iterdir():
        name: tuple[int, ...] | str = parse_number(
            item_directory.name.partition("_")[0]
        )
        details: Path = item_directory / "Details.md"
        if not isinstance(name, str) and details.is_file():
            numbered.append((name, item_directory))
    for _, item_directory in sorted(numbered):
        try:
            title: object = read_item(item_directory).get("title")
        except (OSError, ValueError):
            title = None
        fallback: str = (
            str(title)
            if isinstance(title, str) and title
            else item_directory.name.partition("_")[2].replace("_", " ")
        )
        details = item_directory / "Details.md"
        offered.append((rule_title(details, fallback), details))
    return offered


# Function `parse_choices()`:
def parse_choices(text: str, count: int) -> list[int] | str:
    """Return the numbers that a list of choices gives.

    The choices are numbers and `FROM-TO` ranges, separated by commas
    or spaces (e.g. "1,3-5" or "1 3-5"), each from 1 to `count`.

    Arguments:
    * `text` (`str`):
      The choices.
    * `count` (`int`):
      How many things there are to choose from.

    Returns:
    * (`list[int] | str`): The numbers chosen, sorted and without
      repeats (empty if `text` is), or an error string.
    """
    # Read each number or range, which must be in order and in range.
    chosen: set[int] = set()
    word: str
    for word in re.split(r"[,\s]+", text.strip()):
        if not word:
            continue
        first: str
        dash: str
        last: str
        first, dash, last = word.partition("-")
        if (
            not first.isdecimal()
            or (dash and not last.isdecimal())
            or not 1 <= int(first) <= int(last if dash else first) <= count
        ):
            return (
                f"Invalid choice '{word}': choose numbers from 1 to {count}, "
                "or ranges like 2-4, separated by commas or spaces"
            )
        chosen.update(range(int(first), int(last if dash else first) + 1))
    return sorted(chosen)


# Function `source_name_error()`:
def source_name_error(path: Path) -> str:
    """Return why a file can not be the source of a rule, if it can not.

    A source must be a Markdown file (ending in `.md`), and can not be
    hidden, have one of the `RESERVED_NAMES` (its copy goes into an
    item directory) or be one of the `CLAUDE_NAMES` (Claude Code loads
    it by itself).  The exception is a rule's `Details.md` in a rules
    collection (see `is_rule_copy()`), so that rules can be copied from
    another project.

    Arguments:
    * `path` (`Path`):
      The source file.

    Returns:
    * (`str`): An error string, or an empty string if the name is
      usable.
    """
    if (
        path.name in RESERVED_NAMES and not is_rule_copy(path)
    ) or path.name.startswith("."):
        return f"A source can not be named '{path.name}'"
    if path.suffix != ".md" or path.stem == "":
        return (
            f"'{path.as_posix()}' can not be a rule, since its name does not "
            "end in .md"
        )
    if path.name.casefold() in CLAUDE_NAMES:
        return (
            f"'{path.as_posix()}' can not be a rule, since Claude Code loads "
            f"{path.name} files by itself"
        )
    return ""


# Function `source_doubts()`:
def source_doubts(path: Path) -> str:
    """Return why a file looks like it is not meant to be a rule.

    A file named in capital letters (e.g. `README.md`) is usually about
    the project, and a file with an `@` import of a file (relative to
    its own directory) does not stand alone.

    Arguments:
    * `path` (`Path`):
      The source file.

    Returns:
    * (`str`): The reasons, or an empty string if there are none.
    """
    # A name in capital letters is about the project.
    reasons: list[str] = []
    if CAPITALS_PATTERN.fullmatch(path.stem):
        reasons.append("a project file name")

    # An import of a file means the file does not stand alone; a file
    # that can not be read is reported when it is copied.
    try:
        text: str = read_file(path)
    except (OSError, ValueError):
        text = ""
    imports: list[str] = [
        f"@{imported}"
        for _, imported in markdown_imports(text)
        if (path.parent / Path(imported).expanduser()).is_file()
    ]
    if imports:
        reasons.append(f"imports {', '.join(imports)}")

    # Return the reasons.
    return "; ".join(reasons)


# Function `screen_sources()`:
def screen_sources(
    paths: list[Path], ask: Callable[[str], str]
) -> list[Path] | str:
    """Return the files that may become rules, asking about doubtful ones.

    A file that can not be a source (see `source_name_error()`) is an
    error, so that nothing is created.  The files that look like they
    are not meant to be rules (see `source_doubts()`) are listed in one
    question, and are left out unless the user answers yes.

    Arguments:
    * `paths` (`list[Path]`):
      The source files.
    * `ask` (`Callable[[str], str]`):
      Asks the user a question and returns the answer.

    Returns:
    * (`list[Path] | str`): The files to use, or an error string if
      there are none.
    """
    # Refuse a file that can never be a source.
    path: Path
    for path in paths:
        error: str = source_name_error(path)
        if error:
            return error

    # Find the doubtful files.
    doubts: dict[Path, str] = {}
    for path in paths:
        reasons: str = source_doubts(path)
        if reasons:
            doubts[path] = reasons
    if not doubts:
        return paths

    # Ask once about all of them.
    listed: str = "".join(
        f"  '{path.as_posix()}': {reasons}\n"
        for path, reasons in doubts.items()
    )
    try:
        answer: str = ask(
            "These do not look like rules:\n"
            f"{listed}Make rules from them anyway? [y/N] "
        )
    except EOFError:
        answer = ""
    if answer.strip().casefold() in ("y", "yes"):
        return paths

    # Leave them out.
    kept: list[Path] = [path for path in paths if path not in doubts]
    print(
        f"Skipped {', '.join(repr(path.as_posix()) for path in doubts)}",
        file=sys.stderr,
    )
    return kept or "No rules were created"


# Function `base_tag()`:
def base_tag(title: str) -> str:
    """Return the tag for a title, before it is made unique.

    The tag is the first letter or digit of each word in lower case.
    Punctuation is dropped, a hyphenated word only gives its first
    letter, and the words in `TAG_IGNORED_WORDS` are left out.  If every
    word is left out, the first letter or digit of `title` is used.

    Arguments:
    * `title` (`str`):
      The item's title.

    Returns:
    * (`str`): The tag, without a collection prefix.
    """
    # Take the first letter or digit of each word that is kept.
    tag: str = ""
    word: str
    for word in title.split():
        characters: str = "".join(
            character for character in word if character.isalnum()
        ).casefold()
        if characters and characters not in TAG_IGNORED_WORDS:
            tag += characters[0]

    # Fall back to the first letter or digit of the title.
    if not tag:
        tag = next(
            (character for character in title if character.isalnum()), ""
        ).casefold()
    return tag


# Function `unique_tag()`:
def unique_tag(base: str, used: Iterable[str]) -> str:
    """Return a tag that is not already used.

    Arguments:
    * `base` (`str`):
      The tag from `base_tag()`.
    * `used` (`Iterable[str]`):
      The tags already in use.

    Returns:
    * (`str`): `base`, or `base` plus the lowest number from 2 that
      makes it unused.
    """
    # An unused tag is kept as it is.
    used_tags: set[str] = set(used)
    if base not in used_tags:
        return base

    # Otherwise add the lowest number that makes it unused.
    number: int = 2
    while f"{base}{number}" in used_tags:
        number += 1
    return f"{base}{number}"


# Function `parse_priority()`:
def parse_priority(level: str) -> int | None | str:
    """Convert a priority level like "2" into 2, or "-" into `None`.

    Arguments:
    * `level` (`str`):
      The priority level.

    Returns:
    * (`int | None | str`): The priority, `None` for no priority, or an
      error string if `level` is not a valid priority.
    """
    # A "-" means no priority.
    if level == "-":
        return None

    # Otherwise the level must be one of `PRIORITIES`.
    if level.isdecimal() and int(level) in PRIORITIES:
        return int(level)
    return (
        f"Invalid priority '{level}': it must be one of "
        f"{', '.join(str(priority) for priority in PRIORITIES)} or -"
    )


# Function `number_text()`:
def number_text(name: tuple[int, ...]) -> str:
    """Return an item name as period separated numbers, like "1.2.3".

    Arguments:
    * `name` (`tuple[int, ...]`):
      The item name.

    Returns:
    * (`str`): The item number.
    """
    return ".".join(str(part) for part in name)


# Function `tag_prefix()`:
def tag_prefix(collection_name: str) -> str:
    """Return the tag prefix of a collection, like "T." for "TASKS".

    Arguments:
    * `collection_name` (`str`):
      The name of the collection.

    Returns:
    * (`str`): The tag prefix.
    """
    return f"{collection_name[:1].upper()}."


# Function `tag_collection()`:
def tag_collection(word: str, names: list[str]) -> str:
    """Return the collection whose tag prefix starts a word.

    Arguments:
    * `word` (`str`):
      The word, which may be a tag like "I.dbzib".
    * `names` (`list[str]`):
      The names of the collections.

    Returns:
    * (`str`): The collection name, or "" unless `word` looks like a tag
      and its prefix belongs to one of the `names`.
    """
    # A tag has a one letter prefix and a period.
    if len(word) < 3 or word[1] != ".":
        return ""

    # Find the collection with that prefix.
    return next(
        (name for name in names if tag_prefix(name) == word[:2].upper()), ""
    )


# Function `summary_heading()`:
def summary_heading(tag: str, title: str) -> str:
    """Return the first line of an item's `Summary.md`.

    Arguments:
    * `tag` (`str`):
      The item's tag, with its collection prefix.
    * `title` (`str`):
      The item's title.

    Returns:
    * (`str`): The heading line.
    """
    return f"# Summary of `{tag}` {title}"


# Function `write_summary_heading()`:
def write_summary_heading(item_directory: Path, heading: str) -> None:
    """Make a heading the first line of an item's `Summary.md`.

    The old heading is replaced, or the file is made if it is missing.

    Arguments:
    * `item_directory` (`Path`):
      The item's directory.
    * `heading` (`str`):
      The new heading line.

    Raises:
    * `OSError`: If the file can not be read or written.
    """
    # Read the old summary, if any, and split off its heading.
    path: Path = item_directory / "Summary.md"
    text: str = read_file(path) if path.exists() else ""
    first: str
    rest: str
    first, _, rest = text.partition("\n")

    # Replace the heading, or add one if there was none.
    if not first.startswith("# Summary of "):
        rest = text
    write_file(path, f"{heading}\n{rest}")


# Function `has_summary()`:
def has_summary(item_directory: Path) -> bool:
    """Return whether an item's `Summary.md` says more than its heading.

    Arguments:
    * `item_directory` (`Path`):
      The item's directory.

    Returns:
    * (`bool`): True if the summary has text below its heading.
    """
    # A missing summary says nothing.
    try:
        text: str = read_file(item_directory / "Summary.md")
    except OSError:
        return False

    # Look for text below the heading.
    if text.startswith("# Summary of "):
        text = text.partition("\n")[2]
    return bool(text.strip())


# Function `tag_references()`:
def tag_references(root: Path, tag: str) -> list[Path]:
    """Return the writable `.md` files that mention a tag.

    Only two places are searched, so that a big project tree is never
    walked: the `.md` files directly in `root`, and every `.md` file in
    each collection in `root`.  A file in a hidden directory, a file
    reached through a symbolic link (the file itself or any directory
    on the way), and the generated `RULES_FILE` in each collection are
    skipped.  A mention is the whole tag, so "T.fbm" is not found in
    "T.fbm2" or "XT.fbm".

    Arguments:
    * `root` (`Path`):
      The directory that holds the collections.
    * `tag` (`str`):
      The tag, with its collection prefix.

    Returns:
    * (`list[Path]`): The files that mention `tag`, sorted.
    """
    # Gather the `.md` files directly in `root` and in each collection.
    paths: set[Path] = set(root.glob("*.md"))
    collection: Path
    for collection in sorted(
        marker.parent for marker in root.glob(f"*/{COLLECTION_FILE}")
    ):
        if collection.is_symlink():
            continue
        path: Path
        for path in collection.rglob("*.md"):
            relative: tuple[str, ...] = path.relative_to(collection).parts
            if (
                not any(part.startswith(".") for part in relative)
                and relative != (RULES_FILE,)
                and not any(
                    (collection / Path(*relative[:end])).is_symlink()
                    for end in range(1, len(relative))
                )
            ):
                paths.add(path)

    # Search each writable Markdown file that is not a link.
    pattern: re.Pattern[str] = tag_pattern(tag)
    found: list[Path] = []
    for path in sorted(paths, key=Path.as_posix):
        if (
            path.is_file()
            and not path.is_symlink()
            and os.access(path, os.W_OK)
        ):
            with contextlib.suppress(OSError, UnicodeDecodeError):
                if pattern.search(read_file(path)):
                    found.append(path)

    # Return the files that mention the tag.
    return found


# Function `tag_pattern()`:
def tag_pattern(tag: str) -> re.Pattern[str]:
    """Return a pattern that finds a whole tag in text.

    Arguments:
    * `tag` (`str`):
      The tag, with its collection prefix.

    Returns:
    * (`re.Pattern[str]`): The pattern.
    """
    return re.compile(rf"(?<![\w.]){re.escape(tag)}(?!\w)")


# Function `parse_number()`:
def parse_number(number: str) -> tuple[int, ...] | str:
    """Convert an item number like "1.2.3" into a name like (1, 2, 3).

    Arguments:
    * `number` (`str`):
      The item number.

    Returns:
    * (`tuple[int, ...] | str`): The name, or an error string if the
      number is invalid.
    """
    # An empty number is invalid.
    if not number:
        return "Item number is empty"

    # Each part must be a positive integer.
    name_list: list[int] = []
    part: str
    for part in number.split("."):
        if not part.isdecimal() or int(part) <= 0:
            return (
                f"Invalid item number '{number}': it must be "
                "positive integers separated by periods (e.g. 1, 2.3, "
                "or 1.2.3)"
            )
        name_list.append(int(part))
    return tuple(name_list)


# Function `clean_title()`:
def clean_title(title: str) -> str:
    """Return a title cleaned up for use in an item directory name.

    Hyphens and underscores separate words, periods are kept, other
    punctuation is removed, a word with no letters or digits is dropped,
    the first word is capitalized and the words are joined by
    underscores.  The result can be pasted into a shell command without
    quoting.

    Arguments:
    * `title` (`str`):
      The title.

    Returns:
    * (`str`): The cleaned title, or "" if `title` has no words.
    """
    # Split the title into words, dropping punctuation.
    remove: str = (
        string.punctuation.replace("-", "").replace("_", "").replace(".", "")
    )
    words: list[str] = [
        word
        for word in title.translate(str.maketrans("-_", "  ", remove)).split()
        if any(character.isalnum() for character in word)
    ]

    # A title with no words gives an empty string.
    if not words:
        return ""

    # Capitalize the first word and join the words with underscores.
    words[0] = words[0][0].upper() + words[0][1:]
    return "_".join(words)


# Function `parse_recursive()`:
def parse_recursive(
    command: str,
    arguments: list[str],
    resolve: Callable[[str], list[tuple[int, ...]] | str],
) -> tuple[list[tuple[int, ...]], bool] | str:
    """Parse the `[-r] NUMBER` arguments of a command.

    Arguments:
    * `command` (`str`):
      The command, for the usage message.
    * `arguments` (`list[str]`):
      The command's arguments.
    * `resolve` (`Callable[[str], list[tuple[int, ...]] | str]`):
      Converts a number, tag or range into item names or an error
      string.

    Returns:
    * (`tuple[list[tuple[int, ...]], bool] | str`): The item names and
      whether `-r` was given, or an error string.
    """
    # Separate the `-r` option from the number.
    recursive: bool = False
    numbers: list[str] = []
    argument: str
    for argument in arguments:
        if argument in ("-r", "--recursive"):
            recursive = True
        else:
            numbers.append(argument)

    # There must be exactly one number.
    if len(numbers) != 1:
        return f"Usage: ai_contexts COLLECTION {command} [-r] NUMBER"

    # Resolve the number, tag or range.
    names: list[tuple[int, ...]] | str = resolve(numbers[0])
    if isinstance(names, str):
        return names
    return names, recursive


# Class `Item`:
@dataclass(slots=True)
class Item:
    """A single item.

    Attributes:
    * `name` (`tuple[int, ...]`): The item's number, like `(1, 2, 3)`.
    * `title` (`str`): The one line title.
    * `state` (`str`): The item's state, like "Open".
    * `created` (`str`): When the item was created (UTC), or "".
    * `updated` (`str`): When the item was last updated (UTC), or "".
    * `tag` (`str`): The tag without its collection prefix, or "".
    * `priority` (`int | None`): The priority from 0 to 3, or `None`
      for none.
    * `source` (`str`): The source file of a rule, or "".

    Constructor:
    * `Item(name, title, state, created, updated, tag, priority,
      source)`
    """

    # Constructor arguments:
    name: tuple[int, ...] = field(init=True)
    title: str = field(init=True)
    state: str = field(init=True, default="Pending")
    created: str = field(init=True, default="")
    updated: str = field(init=True, default="")
    tag: str = field(init=True, default="")
    priority: int | None = field(init=True, default=None)
    source: str = field(init=True, default="")

    # Method `Item.__post_init__()`:
    def __post_init__(self) -> None:
        """Ensure that the name and state are valid.

        `Items` also checks that the state is one of its type's states.

        Raises:
        * `ValueError`: If the name is not a non-empty tuple of positive
          integers, or the state is not one of `ALL_STATES`.
        """
        # The name must be a non-empty tuple of positive integers.
        if not (
            isinstance(self.name, tuple)
            and self.name
            and all(
                isinstance(part, int)
                and not isinstance(part, bool)
                and part > 0
                for part in self.name
            )
        ):
            raise ValueError(
                f"Item name {self.name!r} is not a non-empty tuple of "
                "positive integers"
            )

        # The state must be a known state.
        if self.state not in ALL_STATES:
            raise ValueError(
                f"Item state {self.state!r} is not one of "
                f"{', '.join(ALL_STATES)}"
            )

    # Method `Item.number()`:
    @property
    def number(self) -> str:
        """Return the name as period separated numbers.

        Returns:
        * (`str`): The item number, like "1.2.3".
        """
        return ".".join(str(part) for part in self.name)


# Class `Items`:
class Items:
    """A collection of items.

    Attributes:
    * `items_directory` (`Path`): The collection's directory.
    * `items` (`dict[tuple[int, ...], Item]`): The items, by number.
    * `directories` (`dict[tuple[int, ...], Path]`): The directory of
      each item, by number.
    * `error` (`str`): Why the collection can not be used, or "".
    * `settings` (`dict[str, object]`): The settings from
      `.ai_contexts.json`.
    """

    # Method `Items.__init__()`:
    def __init__(self, items_directory: Path) -> None:
        """Initialize the collection of items in a directory.

        The directory and its `.ai_contexts.json` file are created if
        they are not already present.  If the directory can not be
        created or is not writable, an error is printed to stderr and
        `self.error` is set to a non-empty error string.

        Arguments:
        * `items_directory` (`Path`):
          The collection's directory.
        """
        # Start with no items.
        self.items_directory: Path = items_directory
        self.items: dict[tuple[int, ...], Item] = {}
        self.directories: dict[tuple[int, ...], Path] = {}
        self.error: str = ""

        # Create the directory and its `.ai_contexts.json`, if needed.
        collection_path: Path = items_directory / COLLECTION_FILE
        try:
            items_directory.mkdir(exist_ok=True)
            if not os.access(items_directory, os.W_OK):
                self.error = (
                    f"No write access to directory '{items_directory}'"
                )
            elif not collection_path.exists():
                write_file(
                    collection_path,
                    json.dumps({"version": FORMAT_VERSION}, indent=2) + "\n",
                )
        except OSError as error:
            self.error = (
                f"Unable to create directory '{items_directory}': {error}"
            )

        # Read the settings: a JSON object with a known type.
        self.settings: dict[str, object] = {}
        if not self.error:
            try:
                settings: object = json.loads(read_file(collection_path))
            except (OSError, ValueError) as error:
                self.error = f"Unable to read '{collection_path}': {error}"
            else:
                if isinstance(settings, dict):
                    self.settings = settings
                    self.check_version()
                    if self.collection_type_name not in TYPES:
                        self.error = (
                            f"'{collection_path}' has the unknown type "
                            f"{self.collection_type_name!r}; the types "
                            f"are: {', '.join(TYPES)}"
                        )
                else:
                    self.error = (
                        f"Unable to read '{collection_path}': "
                        "it is not a JSON object"
                    )

        # Report an error, or else load the items.
        if self.error:
            print(self.error, file=sys.stderr)
        else:
            recover_transfers(items_directory.parent)
            self.recover_renumber()
            self.load_items()

    # Method `Items.check_version()`:
    def check_version(self) -> None:
        """Check the format version in `.ai_contexts.json`.

        A collection made before versions existed is given
        `FORMAT_VERSION`; any other version than that is reported to
        stderr, as is a failure to write the version.
        """
        # Add a missing version, or report a different one.
        version: object = self.settings.get("version")
        error: str = ""
        if version is None:
            error = self.save_settings(
                {"version": FORMAT_VERSION, **self.settings}
            )
        elif version != FORMAT_VERSION:
            error = (
                f"'{self.items_directory / COLLECTION_FILE}' has version "
                f"{version!r}, but this ai_contexts uses version "
                f"{FORMAT_VERSION}"
            )

        # Report any error.
        if error:
            print(error, file=sys.stderr)

    # Method `Items.prefix()`:
    @property
    def prefix(self) -> str:
        """Return the tag prefix of this collection.

        Returns:
        * (`str`): The tag prefix, like "T.".
        """
        return tag_prefix(self.items_directory.name)

    # Method `Items.collection_type_name()`:
    @property
    def collection_type_name(self) -> str:
        """Return the name of this collection's type.

        Returns:
        * (`str`): The type name, like "items".
        """
        return str(self.settings.get("type", DEFAULT_TYPE))

    # Method `Items.collection_type()`:
    @property
    def collection_type(self) -> CollectionType:
        """Return this collection's type.

        Returns:
        * (`CollectionType`): The type.
        """
        return TYPES[self.collection_type_name]

    # Method `Items.resolve()`:
    def resolve(self, word: str) -> tuple[int, ...] | str:
        """Return the name of the item that a word gives.

        Arguments:
        * `word` (`str`):
          An item number like "1.2.3", or a tag with or without the
          collection prefix, in any case (e.g. "T.fbm" or "fbm").  A
          tag may be followed by "~" and the number it had when it was
          written (e.g. "T.fbm~1.2"), which is checked but not used.

        Returns:
        * (`tuple[int, ...] | str`): The item name, or an error string
          if `word` is neither.
        """
        # A word of digits and periods is a number.
        if word and all(
            character.isdecimal() or character == "." for character in word
        ):
            return parse_number(word)

        # Drop the number after a "~", which may be out of date.
        tag: str
        tilde: str
        hint: str
        tag, tilde, hint = word.partition("~")
        if tilde and isinstance(parse_number(hint), str):
            return f"Invalid item number '{hint}' after '~' in '{word}'"

        # Otherwise look for the tag, with or without the prefix.
        folded: str = tag.casefold()
        item: Item
        for item in self.items.values():
            if item.tag and folded in (
                item.tag.casefold(),
                f"{self.prefix}{item.tag}".casefold(),
            ):
                return item.name

        # The word is neither.
        return f"Invalid item number or tag '{word}'"

    # Method `Items.show()`:
    def show(
        self,
        items: list[Item],
        long: bool = False,
        old_numbers: list[str] | None = None,
    ) -> None:
        """Print items with this collection's tag prefix and priority.

        Arguments:
        * `items` (`list[Item]`):
          The items to print.
        * `long` (`bool`):
          True to also print the created and updated times.
        * `old_numbers` (`list[str] | None`):
          If given, the old number of each item, which is printed first.
        """
        print_items(
            items, long, self.priority_enabled, self.prefix, old_numbers
        )

    # Method `Items.priority_enabled()`:
    @property
    def priority_enabled(self) -> bool:
        """Return whether priority is enabled for this collection.

        Returns:
        * (`bool`): True if priority is enabled.
        """
        return self.settings.get("priority") is True

    # Method `Items.has_file()`:
    def has_file(self, file_name: str) -> bool:
        """Return whether the items of this collection have a file.

        Arguments:
        * `file_name` (`str`):
          The file name, like "Summary.md".

        Returns:
        * (`bool`): True if the collection's type has the file.
        """
        return file_name in self.collection_type.files

    # Method `Items.root()`:
    @property
    def root(self) -> Path:
        """Return the real directory that holds the collections.

        The sources of rules are kept relative to it.

        Returns:
        * (`Path`): The directory.
        """
        return self.items_directory.parent.resolve()

    # Method `Items.copy_path()`:
    def copy_path(self, item: Item) -> Path:
        """Return where the copy of a rule's source goes.

        It is the rule's `Details.md`, so that a rule is read from the
        same file as the details of a task or an issue.

        Arguments:
        * `item` (`Item`):
          The rule.

        Returns:
        * (`Path`): The path of the copy.
        """
        return self.directories[item.name] / "Details.md"

    # Method `Items.upgrade_rule()`:
    def upgrade_rule(self, item: Item) -> None:
        """Move a rule from the old layout to the new one.

        A rule once had a `Details.md` holding only its heading, and a
        copy of its source with the source's name.  Its title goes into
        `.item.json`, the heading-only `Details.md` is removed, and the
        copy becomes `Details.md` (its hash does not change), unless a
        newer copy is already there, when the old one is removed.  What
        was done, or what went wrong, goes to stderr.

        Arguments:
        * `item` (`Item`):
          The rule.
        """
        # Find the rule's files.
        tag: str = f"{self.prefix}{item.tag}"
        item_directory: Path = self.directories[item.name]
        details_path: Path = item_directory / "Details.md"
        old_copy: Path = item_directory / Path(item.source).name
        try:
            # Keep the title in `.item.json`.
            metadata: dict[str, object] = read_item(item_directory)
            if "title" not in metadata:
                metadata["title"] = item.title
                write_item(item_directory, metadata)

            # Remove a `Details.md` that only holds its heading.  A copy
            # of a source is read-only, so it is never taken for one.
            if (
                details_path.is_file()
                and os.access(details_path, os.W_OK)
                and read_file(details_path).count("\n") <= 1
                and read_file(details_path).startswith(f"# {item.number} ")
            ):
                details_path.unlink()

            # Make the copy with the source's name the `Details.md`, or
            # remove it if a newer copy was already made there.
            if item.source and old_copy != details_path and old_copy.is_file():
                if details_path.exists():
                    remove_file(old_copy)
                    print(
                        f"Removed the old copy '{old_copy}' of {tag}",
                        file=sys.stderr,
                    )
                else:
                    old_copy.rename(details_path)
                    print(
                        f"Moved the copy of {tag} to '{details_path}'",
                        file=sys.stderr,
                    )
        except (OSError, ValueError) as error:
            print(f"Unable to upgrade {tag}: {error}", file=sys.stderr)

    # Method `Items.save_settings()`:
    def save_settings(self, settings: dict[str, object]) -> str:
        """Write settings to `.ai_contexts.json` and keep them.

        Arguments:
        * `settings` (`dict[str, object]`):
          The new settings.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Write the settings.
        collection_path: Path = self.items_directory / COLLECTION_FILE
        try:
            write_file(collection_path, json.dumps(settings, indent=2) + "\n")
        except OSError as error:
            return f"Unable to write '{collection_path}': {error}"

        # Keep them once they are written.
        self.settings = settings
        return ""

    # Method `Items.set_feature()`:
    def set_feature(self, feature: str, enabled: bool) -> str:
        """Enable or disable a feature in `.ai_contexts.json`.

        Arguments:
        * `feature` (`str`):
          The feature, like "priority".
        * `enabled` (`bool`):
          True to enable it, False to disable it.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        return self.save_settings({**self.settings, feature: enabled})

    # Method `Items.confirm_snapshot()`:
    def confirm_snapshot(self, ask: Callable[[str], str]) -> bool:
        """Before a move, rename or transfer, recommend a snapshot.

        If there has been no move, rename or transfer in this collection
        for `MOVE_RENAME_DELAY_SECONDS` (or the seconds in the
        `DELAY_VARIABLE` environment variable), a reminder is printed to
        stderr and the user is asked whether to continue.

        Arguments:
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`bool`): True to go ahead.
        """
        # Get the delay, which the test suite can change.
        delay: float = MOVE_RENAME_DELAY_SECONDS
        with contextlib.suppress(ValueError):
            delay = float(os.environ.get(DELAY_VARIABLE, delay))

        # Find how long ago the last move, rename or transfer was.
        last: object = self.settings.get("last_move_or_rename")
        try:
            elapsed: float = (
                time.time() - datetime.fromisoformat(str(last)).timestamp()
            )
        except ValueError:
            elapsed = delay

        # After the delay, recommend a snapshot and ask to continue.
        if elapsed >= delay:
            print(
                "No move, rename or transfer in "
                f"'{self.items_directory.name}' for "
                + (
                    "over an hour"
                    if delay == MOVE_RENAME_DELAY_SECONDS
                    else f"over {delay:g} seconds"
                )
                + "; consider taking a version control "
                "snapshot (e.g. `git commit`) before moving, renaming or "
                "transferring items.",
                file=sys.stderr,
            )
            try:
                answer: str = ask("Continue? Yes(y) or No(n). ")
            except EOFError:
                answer = ""
            return answer.strip().casefold() in ("y", "yes")

        # Otherwise go ahead without asking.
        return True

    # Method `Items.note_move_or_rename()`:
    def note_move_or_rename(self) -> str:
        """Save the time of a move or rename in `.ai_contexts.json`.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        return self.save_settings(
            {
                **self.settings,
                "last_move_or_rename": utc_stamp(time.time()),
            }
        )

    # Method `Items.load_items()`:
    def load_items(self) -> None:
        """Load the existing items from the item directories.

        A directory that is not a valid item directory is skipped with a
        warning printed to stderr.
        """
        # Load each item directory, skipping any that are not valid.
        item_directory: Path
        for item_directory in sorted(self.items_directory.iterdir()):
            if not item_directory.is_dir():
                continue

            # Get the number and title from the directory name.
            number: str
            cleaned_title: str
            number, _, cleaned_title = item_directory.name.partition("_")
            name: tuple[int, ...] | str = parse_number(number)
            if isinstance(name, str):
                print(f"Skipping '{item_directory}': {name}", file=sys.stderr)
                continue

            # Read the metadata and the `Details.md` heading.  A rule's
            # `Details.md` is the copy of its source, so it is only read
            # for the title of a rule in the old layout (see
            # `upgrade_rule()`).
            title: str = cleaned_title.replace("_", " ")
            sources: bool = self.collection_type.has_sources
            details_path: Path = item_directory / "Details.md"
            try:
                metadata: dict[str, object] = read_item(item_directory)
                state: str = str(metadata.get("state"))
                details: str = (
                    read_file(details_path)
                    if not sources
                    or ("title" not in metadata and details_path.exists())
                    else ""
                )
                heading: str = details.partition("\n")[0]
            except (OSError, ValueError) as error:
                print(f"Skipping '{item_directory}': {error}", file=sys.stderr)
                continue

            # The title in the heading wins over the directory name's,
            # and a rule's title in `.item.json` wins over both.
            prefix: str = f"# {number} "
            if heading.startswith(prefix):
                title = heading[len(prefix) :].strip()
            if sources and isinstance(metadata.get("title"), str):
                title = str(metadata["title"]).strip() or title

            # The state must be one of the type's states.
            states: tuple[str, ...] = self.collection_type.states
            if state not in states:
                print(
                    f"Skipping '{item_directory}': its state {state!r} is "
                    f"not one of {', '.join(states)}",
                    file=sys.stderr,
                )
                continue

            # Make the item, ignoring an invalid priority.
            priority: object = metadata.get("priority")
            # The name and state are valid, so `Item` accepts them.
            self.items[name] = Item(
                name,
                title,
                state,
                str(metadata.get("created", "")),
                str(metadata.get("updated", "")),
                str(metadata.get("tag", "")),
                priority
                if isinstance(priority, int)
                and not isinstance(priority, bool)
                and priority in PRIORITIES
                else None,
                str(metadata.get("source", "")),
            )
            self.directories[name] = item_directory

            # Move a rule in the old layout to the new one.
            if sources:
                self.upgrade_rule(self.items[name])

        # Fix and check what was loaded.
        self.add_missing_tags()
        self.add_missing_summaries()
        self.fix_gaps()
        self.check_items()
        if self.collection_type.has_sources:
            self.check_rules()

    # Method `Items.missing_names()`:
    def missing_names(self) -> list[tuple[int, ...]]:
        """Return the names that are missing from the numbering.

        These are the absent parents of items and the absent earlier
        siblings of items and of their parents.

        Returns:
        * (`list[tuple[int, ...]]`): The missing names, sorted.
        """
        # Find the missing siblings of each item and its ancestors.
        missing: set[tuple[int, ...]] = set()
        name: tuple[int, ...]
        for name in self.items:
            length: int
            for length in range(1, len(name) + 1):
                prefix: tuple[int, ...] = name[:length]
                missing.update(
                    prefix[:-1] + (part,)
                    for part in range(1, prefix[-1] + 1)
                    if prefix[:-1] + (part,) not in self.items
                )

        # Return them in order.
        return sorted(missing)

    # Method `Items.gap_free_names()`:
    def gap_free_names(
        self, names: Iterable[tuple[int, ...]] | None = None
    ) -> dict[tuple[int, ...], tuple[int, ...]]:
        """Return the new name of each item whose name must change.

        Items keep their order.  An item whose parent is missing becomes
        a child of its nearest existing ancestor.

        Arguments:
        * `names` (`Iterable[tuple[int, ...]] | None`):
          The names of the items, or `None` for all of them.

        Returns:
        * (`dict[tuple[int, ...], tuple[int, ...]]`): The new name of
          each item whose name changes.
        """
        # Renumber the items in order, under their nearest ancestors.
        present: set[tuple[int, ...]] = set(
            self.items if names is None else names
        )
        new_names: dict[tuple[int, ...], tuple[int, ...]] = {}
        counts: dict[tuple[int, ...], int] = {}
        name: tuple[int, ...]
        for name in sorted(present):
            parent: tuple[int, ...] = next(
                (
                    name[:length]
                    for length in range(len(name) - 1, 0, -1)
                    if name[:length] in present
                ),
                (),
            )
            new_parent: tuple[int, ...] = new_names[parent] if parent else ()
            counts[new_parent] = counts.get(new_parent, 0) + 1
            new_names[name] = new_parent + (counts[new_parent],)

        # Keep only the names that change.
        return {old: new for old, new in new_names.items() if old != new}

    # Method `Items.renumber()`:
    def renumber(
        self, new_names: dict[tuple[int, ...], tuple[int, ...]]
    ) -> str:
        """Give items their new names.

        Each item directory is renamed (via a temporary name, so that
        the new names can not collide with the old ones) and the heading
        of its `Details.md` is rewritten.  The plan is first written to
        `.renumber.json`, which is removed at the end, so that an
        interrupted renumbering is finished the next time the collection
        is loaded.

        Arguments:
        * `new_names` (`dict[tuple[int, ...], tuple[int, ...]]`):
          The new name of each item to rename.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # There is nothing to do without new names.
        if not new_names:
            return ""

        # Do the renumbering, from its first phase.
        renames: list[dict[str, str]] = self.rename_records(new_names)
        error: str = do_renumber(self.items_directory, renames, 1)
        if error and not (self.items_directory / RENUMBER_FILE).exists():
            return error

        # Even after a failure, the items are where the plan puts them,
        # since the next load finishes the plan.
        self.apply_renames(new_names)
        return error

    # Method `Items.rename_records()`:
    def rename_records(
        self, new_names: dict[tuple[int, ...], tuple[int, ...]]
    ) -> list[dict[str, str]]:
        """Return the renames that give items their new names.

        Arguments:
        * `new_names` (`dict[tuple[int, ...], tuple[int, ...]]`):
          The new name of each item to rename.

        Returns:
        * (`list[dict[str, str]]`): The renames, in name order, each
          with the `RENAME_KEYS` of `.renumber.json`.
        """
        # Rename each item via a temporary name, in name order.
        renames: list[dict[str, str]] = []
        index: int
        old: tuple[int, ...]
        for index, old in enumerate(sorted(new_names)):
            title_part: str = self.directories[old].name.partition("_")[2]
            renames.append(
                {
                    "old": self.directories[old].name,
                    "temporary": f".renumber_{index}",
                    "new": f"{number_text(new_names[old])}_{title_part}",
                    "old_number": number_text(old),
                    "new_number": number_text(new_names[old]),
                }
            )

        # Return the renames.
        return renames

    # Method `Items.apply_renames()`:
    def apply_renames(
        self, new_names: dict[tuple[int, ...], tuple[int, ...]]
    ) -> None:
        """Give items their new names in memory.

        This is done after their directories are renamed.

        Arguments:
        * `new_names` (`dict[tuple[int, ...], tuple[int, ...]]`):
          The new name of each renamed item.
        """
        # Remove the moving items from their old names.
        moving: list[Item] = [self.items[old] for old in sorted(new_names)]
        directories: list[Path] = [
            self.directories[item.name] for item in moving
        ]
        item: Item
        for item in moving:
            del self.items[item.name]
            del self.directories[item.name]

        # Add them back with their new names and directories.
        directory: Path
        for item, directory in zip(moving, directories, strict=True):
            item.name = new_names[item.name]
            self.items[item.name] = item
            self.directories[item.name] = (
                self.items_directory
                / f"{item.number}_{directory.name.partition('_')[2]}"
            )

    # Method `Items.recover_renumber()`:
    def recover_renumber(self) -> None:
        """Finish an interrupted renumbering, if there is one.

        The recovery, or a failure to recover, is reported to stderr.
        """
        # There is nothing to do without a plan.
        marker: Path = self.items_directory / RENUMBER_FILE
        if not marker.exists():
            return

        # Read the plan and finish it.
        error: str = ""
        try:
            plan: object = json.loads(read_file(marker))
            if not isinstance(plan, dict):
                raise TypeError("it is not a JSON object")
            phase: int = int(str(plan["phase"]))
            renames: list[dict[str, str]] = [
                {key: str(rename[key]) for key in RENAME_KEYS}
                for rename in plan["renames"]
            ]
        except (OSError, ValueError, TypeError, KeyError) as problem:
            error = f"Unable to read '{marker}': {problem!r}"
        else:
            error = do_renumber(self.items_directory, renames, phase)

        # Report the result.
        if error:
            print(
                f"Unable to finish an interrupted renumbering: {error}",
                file=sys.stderr,
            )
        else:
            print(
                f"Finished an interrupted renumbering in "
                f"'{self.items_directory}': "
                + ", ".join(
                    f"{rename['old_number']} -> {rename['new_number']}"
                    for rename in renames
                ),
                file=sys.stderr,
            )

    # Method `Items.check_items()`:
    def check_items(self) -> None:
        """Check the items each time the collection is loaded.

        What ai_contexts maintains is fixed: the number in the `# N
        Title` heading of `Details.md` and the heading of `Summary.md`.
        What a human maintains is reported, with what to do about it: a
        `Details.md` without that heading, a title that no longer
        matches the directory name, and items that share a tag.
        Everything goes to stderr.
        """
        # Check each item, noting the numbers that use each tag.
        messages: list[str] = []
        tags: dict[str, list[str]] = {}
        item: Item
        for item in self.list_items():
            # Note where the item is and the number that uses its tag.
            item_directory: Path = self.directories[item.name]
            where: str = f"'{item_directory}'"
            tags.setdefault(item.tag, []).append(item.number)

            # Fix or report the number in the `Details.md` heading.  A
            # rule's `Details.md` is the copy of its source, with its
            # source's heading, so it is left alone.
            try:
                details_path: Path = item_directory / "Details.md"
                if not self.collection_type.has_sources:
                    details: str = read_file(details_path)
                    heading: str
                    rest: str
                    heading, _, rest = details.partition("\n")
                    words: list[str] = heading.split(" ", 2)
                    if (
                        len(words) == 3
                        and words[0] == "#"
                        and words[1] != item.number
                        and not isinstance(parse_number(words[1]), str)
                    ):
                        write_file(
                            details_path,
                            f"# {item.number} {words[2]}\n{rest}",
                        )
                        item.title = words[2].strip()
                        messages.append(
                            f"Fixed the item number in the heading of {where}"
                        )
                    elif not heading.startswith(f"# {item.number} "):
                        messages.append(
                            f"{where}: its Details.md does not start with a "
                            f"'# {item.number} TITLE' heading; `ai_contexts "
                            f"{self.prefix}{item.tag} rename to TITLE` adds "
                            "one"
                        )

                # Report a title that does not match the directory.
                if (
                    clean_title(item.title)
                    != item_directory.name.partition("_")[2]
                ):
                    messages.append(
                        f"{where}: its directory name does not match its "
                        f"title '{item.title}'; `ai_contexts "
                        f"{self.prefix}{item.tag} rename to {item.title}` "
                        "fixes it"
                    )

                # Fix a stale `Summary.md` heading.
                summary: str = summary_heading(
                    f"{self.prefix}{item.tag}", item.title
                )
                summary_path: Path = item_directory / "Summary.md"
                if (
                    self.has_file("Summary.md")
                    and summary_path.exists()
                    and read_file(summary_path).partition("\n")[0] != summary
                ):
                    write_summary_heading(item_directory, summary)
                    messages.append(f"Fixed the heading of {where}/Summary.md")
            except OSError as error:
                messages.append(f"Unable to check {where}: {error}")

        # Report the tags shared by more than one item.
        tag: str
        numbers: list[str]
        for tag, numbers in sorted(tags.items()):
            if len(numbers) > 1:
                messages.append(
                    f"Items {', '.join(numbers)} in '{self.items_directory}' "
                    f"share the tag {self.prefix}{tag}; rename one of them"
                )

        # Print every message.
        message: str
        for message in messages:
            print(message, file=sys.stderr)

    # Method `Items.check_rules()`:
    def check_rules(self) -> None:
        """Refresh and check the copies of the rules' sources.

        Each rule with a source has its copy refreshed (see
        `refresh_rule()`).  A rule without a source, an Active rule
        without a copy, a copy with an `@` import of a file (relative to
        the source; a rule must stand alone) and a copy that is the same
        as a file that `CLAUDE.md` imports directly are reported.
        Everything goes to stderr.
        """
        # Check each rule, collecting messages.
        messages: list[str] = []
        imported: dict[str, str] = self.claude_imports()
        item: Item
        for item in self.list_items():
            # A rule needs a source.
            tag: str = f"{self.prefix}{item.tag}"
            if not item.source:
                messages.append(
                    f"{tag} has no source; `ai_contexts {tag} source PATH` "
                    "sets one"
                )
                continue

            # Refresh the copy of the source.
            message: str = self.refresh_rule(item)
            if message:
                messages.append(message)

            # An Active rule needs a copy.
            copy_path: Path = self.copy_path(item)
            if not copy_path.is_file():
                if item.state == "Active":
                    messages.append(
                        f"{tag} is Active but has no copy of its source "
                        f"'{item.source}'"
                    )
                continue

            # Read the copy.
            try:
                text: str = read_file(copy_path)
                copy_hash: str = sha256_of(copy_path)
            except (OSError, ValueError) as error:
                messages.append(f"Unable to check {tag}: {error}")
                continue

            # A rule must not import a file.
            source_directory: Path = (self.root / item.source).parent
            number: int
            path: str
            for number, path in markdown_imports(text):
                if (source_directory / Path(path).expanduser()).is_file():
                    messages.append(
                        f"{tag}: its copy imports @{path} (line {number}); "
                        "a rule must stand alone"
                    )

            # Report a copy that `CLAUDE.md` also imports.
            same: str = imported.get(copy_hash, "")
            if same:
                messages.append(
                    f"{tag} is the same as '{same}', which CLAUDE.md also "
                    "imports"
                )

        # Print every message.
        for message in messages:
            print(message, file=sys.stderr)

    # Method `Items.claude_imports()`:
    def claude_imports(self) -> dict[str, str]:
        """Return the files that `CLAUDE.md` imports.

        `CLAUDE.md` is in the directory that holds the collections.  An
        import that is not a readable file is left out.

        Returns:
        * (`dict[str, str]`): The imported files, keyed by SHA-256.
        """
        # Read `CLAUDE.md`, if there is one.
        claude: Path = self.items_directory.parent / "CLAUDE.md"
        try:
            text: str = read_file(claude)
        except (OSError, ValueError):
            return {}

        # Hash each file that it imports.
        imported: dict[str, str] = {}
        path: str
        for _, path in markdown_imports(text):
            with contextlib.suppress(OSError):
                imported[
                    sha256_of(claude.parent / Path(path).expanduser())
                ] = path
        return imported

    # Method `Items.refresh_rule()`:
    def refresh_rule(self, item: Item, force: bool = False) -> str:
        """Refresh the copy of the source of a rule.

        The copy is left alone if it is the same as the source (the hash
        is recorded if it was not), or if it was edited in place (its
        hash is not the recorded one) unless `force`, or if the source
        is missing.  Otherwise the source is copied to a temporary file,
        which is made read-only and then replaces the copy, and its hash
        and the time are recorded in `.item.json`.

        Arguments:
        * `item` (`Item`):
          The rule.
        * `force` (`bool`):
          True to replace a copy that was edited in place.

        Returns:
        * (`str`): What was done or what is wrong, or an empty string if
          nothing was done.
        """
        # Find the rule's files.
        tag: str = f"{self.prefix}{item.tag}"
        item_directory: Path = self.directories[item.name]
        source_path: Path = self.root / item.source
        copy_path: Path = self.copy_path(item)

        # Hash the copy and the source.
        try:
            metadata: dict[str, object] = read_item(item_directory)
            recorded: str = str(metadata.get("sha256", ""))
            copy_hash: str = sha256_of(copy_path) if copy_path.exists() else ""
            source: bytes = (
                source_path.read_bytes() if source_path.is_file() else b""
            )
            source_hash: str = (
                hashlib.sha256(source).hexdigest()
                if source_path.is_file()
                else ""
            )

            # A matching copy only needs its hash recorded.
            if copy_hash and copy_hash == source_hash:
                if recorded != copy_hash:
                    metadata["sha256"] = copy_hash
                    metadata.setdefault("refreshed", utc_stamp(time.time()))
                    write_item(item_directory, metadata)
                return ""

            # Keep a copy that was edited in place, unless forced.
            if copy_hash and copy_hash != recorded and not force:
                return (
                    f"{tag}: its copy '{copy_path}' was edited in place; "
                    f"`ai_contexts {tag} refresh` replaces it with its source "
                    f"'{item.source}'"
                )

            # Keep the last copy if the source is missing.
            if not source_hash:
                return f"{tag}: its source '{item.source}' is missing" + (
                    "; its last copy is kept" if copy_hash else ""
                )

            # Replace the copy via a read-only temporary file.
            temporary: Path = item_directory / COPY_TEMPORARY
            remove_file(temporary)
            temporary.write_bytes(source)
            temporary.chmod(0o444)
            make_writable(copy_path)
            temporary.replace(copy_path)

            # Record the new hash and the time.
            metadata["sha256"] = source_hash
            metadata["refreshed"] = utc_stamp(time.time())
            write_item(item_directory, metadata)
        except (OSError, ValueError) as error:
            return f"Unable to refresh {tag}: {error}"

        # Report the refresh.
        return f"Refreshed {tag} from '{item.source}'"

    # Method `Items.fix_gaps()`:
    def fix_gaps(self) -> None:
        """Renumber the items if there are gaps, reporting it to stderr.

        Gaps only appear when item directories are removed by hand.
        """
        # Find the new names that close the gaps.
        new_names: dict[tuple[int, ...], tuple[int, ...]] = (
            self.gap_free_names()
        )
        if not new_names:
            return

        # Report the gaps and the renumbering.
        missing: str = ", ".join(
            number_text(name) for name in self.missing_names()
        )
        changes: str = ", ".join(
            f"{number_text(old)} -> {number_text(new)}"
            for old, new in sorted(new_names.items())
        )
        print(
            f"Gaps found in '{self.items_directory}' ({missing} missing); "
            f"renumbered {changes}",
            file=sys.stderr,
        )

        # Renumber, reporting any error.
        error: str = self.renumber(new_names)
        if error:
            print(error, file=sys.stderr)

    # Method `Items.add_missing_summaries()`:
    def add_missing_summaries(self) -> None:
        """Give an empty `Summary.md` to every item without one.

        This is for items made before `Summary.md` existed, so it is
        only done if the collection's type has a `Summary.md`.  A file
        that can not be written is reported to stderr.
        """
        # Only a type with a `Summary.md` needs one.
        if not self.has_file("Summary.md"):
            return

        # Add a summary to each item without one.
        item: Item
        for item in self.list_items():
            item_directory: Path = self.directories[item.name]
            if (item_directory / "Summary.md").exists():
                continue
            try:
                write_summary_heading(
                    item_directory,
                    summary_heading(f"{self.prefix}{item.tag}", item.title),
                )
            except OSError as error:
                print(
                    f"Unable to add a summary to '{item_directory}': {error}",
                    file=sys.stderr,
                )

    # Method `Items.add_missing_tags()`:
    def add_missing_tags(self) -> None:
        """Give a unique tag to every item that does not have one.

        This is for items made before tags existed, so the updated time
        is not changed.  A tag that can not be written is reported to
        stderr.
        """
        # Tag each item that has no tag.
        item: Item
        for item in self.list_items():
            if item.tag:
                continue

            # Make a tag that no other item has.
            tag: str = unique_tag(
                base_tag(item.title),
                (other.tag for other in self.items.values()),
            )

            # Write the tag, without changing the updated time.
            item_directory: Path = self.directories[item.name]
            try:
                metadata: dict[str, object] = read_item(item_directory)
                metadata["tag"] = tag
                write_item(item_directory, metadata)
            except (OSError, ValueError) as error:
                print(
                    f"Unable to add tag to '{item_directory}': {error}",
                    file=sys.stderr,
                )
                continue

            # Keep the tag in memory once it is written.
            item.tag = tag

    # Method `Items.list_items()`:
    def list_items(self, name: tuple[int, ...] = ()) -> list[Item]:
        """Return an item and its descendants, sorted by name.

        Arguments:
        * `name` (`tuple[int, ...]`):
          The item's name, or `()` for all of the items.

        Returns:
        * (`list[Item]`): The items whose names start with `name`.
        """
        return [
            self.items[item_name]
            for item_name in sorted(self.items)
            if item_name[: len(name)] == name
        ]

    # Method `Items.create_item()`:
    def create_item(
        self, number: str, title: str, place: str = ""
    ) -> Item | str:
        """Create a new item at a number, or before or after an item.

        The later items are renumbered to make room.

        Arguments:
        * `number` (`str`):
          The new item's number, or with `place`, the number or tag of
          an existing item.
        * `title` (`str`):
          The new item's title.
        * `place` (`str`):
          "" to create the item at `number`, or "before" or "after".

        Returns:
        * (`Item | str`): The new item, or an error string if it can not
          be created.
        """
        # A place is handled by `create_at_place()`.
        if place:
            return self.create_at_place(number, title, place)

        # Parse the number.
        name: tuple[int, ...] | str = parse_number(number)
        if isinstance(name, str):
            return name

        # The item and its directory must not exist yet.
        number = ".".join(str(part) for part in name)
        sub_directories: set[str] = {
            path.name.split("_", 1)[0]
            for path in self.items_directory.iterdir()
            if path.is_dir()
        }
        if name in self.items or number in sub_directories:
            return f"Item '{number}' already exists"

        # Its parent must exist.
        if len(name) > 1 and name[:-1] not in self.items:
            return (
                f"Item '{number}' can not be created: "
                f"{number_text(name[:-1])} does not exist"
            )

        # The number must be the next free one.
        free: tuple[int, ...] = name[:-1] + (
            sum(
                1
                for other in self.items
                if len(other) == len(name) and other[:-1] == name[:-1]
            )
            + 1,
        )
        if name != free:
            return (
                f"Item '{number}' would leave a gap; the next free number "
                f"is {number_text(free)}"
            )

        # Make the item.
        return self.make_item(name, title)

    # Method `Items.create_at_place()`:
    def create_at_place(self, word: str, title: str, place: str) -> Item | str:
        """Create a new item before or after an existing item.

        Arguments:
        * `word` (`str`):
          The number or tag of the existing item.
        * `title` (`str`):
          The new item's title.
        * `place` (`str`):
          "before" or "after".

        Returns:
        * (`Item | str`): The new item, or an error string if it can not
          be created.
        """
        # Resolve the existing item.
        target: tuple[int, ...] | str = self.resolve(word)
        if isinstance(target, str):
            return target

        # Plan making room for the new item.
        planned: (
            tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]
            | str
        ) = self.plan_place([], place, target)
        if isinstance(planned, str):
            return planned
        new_names: dict[tuple[int, ...], tuple[int, ...]]
        name: tuple[int, ...]
        new_names, name = planned

        # The title must not be empty.
        if not clean_title(title):
            return f"Item '{number_text(name)}' has an empty title"

        # Make room, then make the item.
        error: str = self.renumber(new_names)
        if error:
            return error
        return self.make_item(name, title)

    # Method `Items.make_item()`:
    def make_item(self, name: tuple[int, ...], title: str) -> Item | str:
        """Make the directory and files of a new item.

        Arguments:
        * `name` (`tuple[int, ...]`):
          The new item's name.
        * `title` (`str`):
          The new item's title.

        Returns:
        * (`Item | str`): The new item, or an error string if it can not
          be made.
        """
        # The title must not be empty.
        number: str = number_text(name)
        title = title.strip()
        cleaned_title: str = clean_title(title)
        if not cleaned_title:
            return f"Item '{number}' has an empty title"

        # Make the item, with a unique tag.
        item_directory: Path = (
            self.items_directory / f"{number}_{cleaned_title}"
        )
        stamp: str = utc_stamp(time.time())
        tag: str = unique_tag(
            base_tag(title), (other.tag for other in self.items.values())
        )
        item: Item = Item(
            name,
            title,
            self.collection_type.new_state,
            created=stamp,
            updated=stamp,
            tag=tag,
        )

        # Write its directory and files.  A rule keeps its title in
        # `.item.json`, since its `Details.md` is the copy of its
        # source.
        sources: bool = self.collection_type.has_sources
        try:
            item_directory.mkdir()
            write_item(
                item_directory,
                {**new_metadata(item.state, stamp), "tag": tag}
                | ({"title": title} if sources else {}),
            )
            if self.has_file("Context.md"):
                write_file(
                    item_directory / "Context.md", "# LLM Agent Context Log\n"
                )
            if not sources:
                write_file(
                    item_directory / "Details.md", f"# {number} {title}\n"
                )
            if self.has_file("Summary.md"):
                write_summary_heading(
                    item_directory,
                    summary_heading(f"{self.prefix}{tag}", title),
                )
        except OSError as error:
            return (
                f"Unable to create item directory '{item_directory}': {error}"
            )

        # Add it to the collection.
        self.items[name] = item
        self.directories[name] = item_directory
        return item

    # Method `Items.select_items()`:
    def select_items(
        self, name: tuple[int, ...], recursive: bool = False
    ) -> list[Item] | str:
        """Return an item, and its descendants if recursive.

        Arguments:
        * `name` (`tuple[int, ...]`):
          The item's name.
        * `recursive` (`bool`):
          True to include the item's descendants.

        Returns:
        * (`list[Item] | str`): The items, or an error string if no item
          matches.
        """
        # Select the item and its descendants, if recursive.
        number: str = ".".join(str(part) for part in name)
        if recursive:
            selected: list[Item] = self.list_items(name)
            if not selected:
                return f"No items match '{number}'"
            return selected

        # Otherwise select the item alone.
        if name in self.items:
            return [self.items[name]]
        return f"Item '{number}' does not exist"

    # Method `Items.rename_item()`:
    def rename_item(self, name: tuple[int, ...], title: str) -> Item | str:
        """Change the title of an item.

        The item directory is renamed to match, and the heading line of
        its `Details.md` is rewritten, or added if it is missing, as is
        the heading of its `Summary.md`.  A rule's title is kept in
        `.item.json` instead, since its `Details.md` is the copy of its
        source.  The tag is made from the new
        title, unless it would be the same as before.  The updated time
        is set to now.

        Arguments:
        * `name` (`tuple[int, ...]`):
          The item's name.
        * `title` (`str`):
          The new title.

        Returns:
        * (`Item | str`): The renamed item, or an error string if it can
          not be renamed.
        """
        # The item must exist and the title must not be empty.
        number: str = ".".join(str(part) for part in name)
        if name not in self.items:
            return f"Item '{number}' does not exist"
        title = title.strip()
        cleaned_title: str = clean_title(title)
        if not cleaned_title:
            return f"Item '{number}' has an empty title"

        # The new directory must not exist.
        old_directory: Path = self.directories[name]
        new_directory: Path = (
            self.items_directory / f"{number}_{cleaned_title}"
        )
        if new_directory != old_directory and new_directory.exists():
            return f"'{new_directory}' already exists"

        # Make a new tag only if the title's tag changes.
        item: Item = self.items[name]
        tag: str = item.tag
        if not tag or base_tag(title) != base_tag(item.title):
            tag = unique_tag(
                base_tag(title),
                (
                    other.tag
                    for other in self.items.values()
                    if other is not item
                ),
            )

        # Rewrite the headings, record the tag and rename the directory.
        sources: bool = self.collection_type.has_sources
        details_path: Path = old_directory / "Details.md"
        try:
            if not sources:
                details: str = read_file(details_path)
                heading: str
                rest: str
                heading, _, rest = details.partition("\n")
                if not heading.startswith(f"# {number} "):
                    rest = details
                write_file(details_path, f"# {number} {title}\n{rest}")
            if self.has_file("Summary.md"):
                write_summary_heading(
                    old_directory,
                    summary_heading(f"{self.prefix}{tag}", title),
                )
            fields: dict[str, object] = {"tag": tag}
            if sources:
                fields["title"] = title
            updated: str = update_item(old_directory, fields=fields)
            old_directory.rename(new_directory)
        except (OSError, ValueError) as error:
            return f"Unable to rename item '{number}': {error}"

        # Update the item in memory.
        item.title = title
        item.tag = tag
        item.updated = updated
        self.directories[name] = new_directory
        return item

    # Method `Items.plan_place()`:
    def plan_place(
        self,
        moving: list[tuple[int, ...]],
        place: str,
        target: tuple[int, ...],
        count: int = 1,
    ) -> tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]] | str:
        """Plan putting sibling items (or new items) at a place.

        The names refer to the items before anything moves.

        Arguments:
        * `moving` (`list[tuple[int, ...]]`):
          The names of the sibling items to move, or empty for new
          items.
        * `place` (`str`):
          "" for the free number `target`, or "before" or "after" the
          existing item `target`.
        * `target` (`tuple[int, ...]`):
          The free number or existing item.
        * `count` (`int`):
          When `moving` is empty, the number of new sibling items to
          make room for, numbered from the first one.

        Returns:
        * (`tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int,
          ...]] | str`): The new name of every item whose name changes
          and the new name of the first moved (or new) item, or an error
          string if the place is not valid.
        """
        # The moving items must exist.
        name: tuple[int, ...]
        for name in moving:
            if name not in self.items:
                return f"Item '{number_text(name)}' does not exist"

        # Find the children of each item.
        children: dict[tuple[int, ...], list[tuple[int, ...]]] = {(): []}
        for name in sorted(self.items):
            children.setdefault(name, [])
            children[name[:-1]].append(name)

        # Find every item that moves, with its descendants.
        moved: set[tuple[int, ...]] = {
            item.name for name in moving for item in self.list_items(name)
        }

        # Find the siblings at the place, which must be valid.
        target_number: str = number_text(target)
        siblings: list[tuple[int, ...]]
        if place:
            if target not in self.items:
                return f"Item '{target_number}' does not exist"
            if target in moved:
                return f"Items can not be moved {place} themselves"
            siblings = children[target[:-1]]
        else:
            if target in self.items:
                return f"Item '{target_number}' already exists"
            parent: tuple[int, ...] = target[:-1]
            if parent not in children:
                return f"Item '{number_text(parent)}' does not exist"
            if parent in moved:
                return "Items can not be moved into themselves"
            if target[-1] != len(children[parent]) + 1:
                return (
                    f"'{target_number}' is not the next free number; that "
                    f"is {number_text(parent + (len(children[parent]) + 1,))}"
                )
            siblings = children[parent]

        # Take the moving items out of their siblings.
        if moving:
            # In place, since `siblings` may be the same list.
            children[moving[0][:-1]][:] = [
                name for name in children[moving[0][:-1]] if name not in moving
            ]

        # Find where the items go among their siblings.
        index: int = (
            siblings.index(target) + (place == "after")
            if place
            else len(siblings)
        )

        # Stand-ins for the new items; no item has a 0 in its name.
        new_items: list[tuple[int, ...]] = [NEW_ITEM] + [
            (0, index) for index in range(1, count)
        ]
        siblings[index:index] = moving or new_items

        # The new items have no children yet.
        new_item: tuple[int, ...]
        for new_item in new_items:
            children[new_item] = []

        # Number every item from the top, depth first.
        new_names: dict[tuple[int, ...], tuple[int, ...]] = {}

        def number(
            parent: tuple[int, ...], new_parent: tuple[int, ...]
        ) -> None:
            """Give the descendants of a parent their new names.

            Arguments:
            * `parent` (`tuple[int, ...]`):
              The parent's old name, or `()` for the top level.
            * `new_parent` (`tuple[int, ...]`):
              The parent's new name.
            """
            position: int
            name: tuple[int, ...]
            for position, name in enumerate(children[parent], 1):
                new_names[name] = new_parent + (position,)
                number(name, new_names[name])

        # Number the items and return the changes.
        number((), ())
        first: tuple[int, ...] = new_names[(moving or new_items)[0]]
        return {
            old: new
            for old, new in new_names.items()
            if old != new and old not in new_items
        }, first

    # Method `Items.resolve_range()`:
    def resolve_range(self, word: str) -> list[tuple[int, ...]] | str:
        """Return the names of the items that a word gives.

        Arguments:
        * `word` (`str`):
          A number or tag (see `resolve()`), or a range of siblings like
          "1.2.5-6".  Every item in a range must exist.

        Returns:
        * (`list[tuple[int, ...]] | str`): The names, or an error string
          if `word` is not valid.
        """
        # A word without a "-" is a single number or tag.
        if "-" not in word:
            name: tuple[int, ...] | str = self.resolve(word)
            return name if isinstance(name, str) else [name]

        # Parse the range, whose last number must be the greater.
        first_text: str
        last_text: str
        first_text, _, last_text = word.rpartition("-")
        first: tuple[int, ...] | str = parse_number(first_text)
        if isinstance(first, str):
            return first
        if not last_text.isdecimal() or int(last_text) <= first[-1]:
            return (
                f"Invalid range '{word}': it must be like 1.2.5-6, with the "
                "last number greater than the one before the '-'"
            )

        # Every item in the range must exist.
        names: list[tuple[int, ...]] = [
            first[:-1] + (part,)
            for part in range(first[-1], int(last_text) + 1)
        ]
        for name in names:
            if name not in self.items:
                return f"Item '{number_text(name)}' does not exist"
        return names

    # Method `Items.delete_items()`:
    def delete_items(
        self,
        names: list[tuple[int, ...]],
        recursive: bool = False,
        ask: Callable[[str], str] = input,
    ) -> tuple[list[Item], dict[str, Item]] | str:
        """Delete items, and their descendants if recursive.

        An item with children is only deleted if `recursive`, and then
        only if the user answers yes.  Each item directory is removed
        along with everything in it, and the later items are renumbered
        so that there are no gaps.

        Arguments:
        * `names` (`list[tuple[int, ...]]`):
          The names of the items to delete.
        * `recursive` (`bool`):
          True to delete the items' descendants too.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`tuple[list[Item], dict[str, Item]] | str`): The deleted
          items and the renumbered items keyed by their old numbers, or
          an error string on failure.
        """
        # The items must exist.
        name: tuple[int, ...]
        for name in names:
            if name not in self.items:
                return f"Item '{number_text(name)}' does not exist"

        # Find every item to delete, with its descendants.
        doomed: list[Item] = [
            item for name in names for item in self.list_items(name)
        ]

        # Without -r, refuse items with children; with -r, ask first.
        if not recursive:
            for name in names:
                if len(self.list_items(name)) > 1:
                    return (
                        f"Item '{number_text(name)}' has children; use -r "
                        "to delete them too"
                    )
        else:
            try:
                answer: str = ask(
                    f"Do you really want to delete {len(doomed)} items "
                    "Yes(y) or No(n). "
                )
            except EOFError:
                answer = ""
            if answer.strip().casefold() not in ("y", "yes"):
                return "Nothing deleted"

        # Remove each item directory.
        item: Item
        for item in doomed:
            item_directory: Path = self.directories[item.name]
            try:
                remove_tree(item_directory)
            except OSError as error:
                return f"Unable to delete '{item_directory}': {error}"
            del self.items[item.name]
            del self.directories[item.name]

        # Close the gaps, noting the renumbered items' old numbers.
        new_names: dict[tuple[int, ...], tuple[int, ...]] = (
            self.gap_free_names()
        )
        renumbered: dict[str, Item] = {
            number_text(old): self.items[old] for old in sorted(new_names)
        }

        # Renumber, then return the deleted and renumbered items.
        failure: str = self.renumber(new_names)
        if failure:
            return failure
        return doomed, renumbered

    # Method `Items.move_items()`:
    def move_items(
        self, names: list[tuple[int, ...]], place: str, target: tuple[int, ...]
    ) -> dict[str, Item] | str:
        """Move sibling items, with their descendants, to a place.

        Arguments:
        * `names` (`list[tuple[int, ...]]`):
          The names of the sibling items to move.
        * `place` (`str`):
          As for `plan_place()`.
        * `target` (`tuple[int, ...]`):
          As for `plan_place()`.

        Returns:
        * (`dict[str, Item] | str`): The renumbered items keyed by their
          old numbers, or an error string on failure.
        """
        # Plan the move, which must be valid.
        planned: (
            tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]
            | str
        ) = self.plan_place(names, place, target)
        if isinstance(planned, str):
            return planned

        # Renumber the items.
        new_names: dict[tuple[int, ...], tuple[int, ...]] = planned[0]
        error: str = self.renumber(new_names)
        if error:
            return error

        # Return the renumbered items by their old numbers.
        return {
            number_text(old): self.items[new]
            for old, new in sorted(new_names.items())
        }

    # Method `Items.check_transfer()`:
    def check_transfer(
        self,
        names: list[tuple[int, ...]],
        target: "Items",
        place: str,
        word: str,
    ) -> tuple[int, ...] | str:
        """Check a transfer of items (see `transfer_items()`).

        Arguments:
        * `names` (`list[tuple[int, ...]]`):
          The names of the sibling items to transfer.
        * `target` (`Items`):
          The collection to transfer them to.
        * `place` (`str`):
          "", "before" or "after".
        * `word` (`str`):
          The number or tag of the place in `target`.

        Returns:
        * (`tuple[int, ...] | str`): The name in `target` of the place
          `word`, or an error string if the transfer is not valid.
        """
        # The target must be another collection of the same type.
        if target.items_directory == self.items_directory:
            return (
                "Items can not be transferred to their own collection; use "
                "move"
            )
        if target.collection_type_name != self.collection_type_name:
            return (
                f"Items can not be transferred from '"
                f"{self.items_directory.name}' (type "
                f"{self.collection_type_name}) to '"
                f"{target.items_directory.name}' (type "
                f"{target.collection_type_name})"
            )

        # The items must exist.
        name: tuple[int, ...]
        for name in names:
            if name not in self.items:
                return f"Item '{number_text(name)}' does not exist"

        # The place in the target must be valid.
        first: tuple[int, ...] | str = (
            target.resolve(word) if place else parse_number(word)
        )
        if isinstance(first, str):
            return first
        planned: (
            tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]
            | str
        ) = target.plan_place([], place, first)
        return planned if isinstance(planned, str) else first

    # Method `Items.transfer_items()`:
    def transfer_items(
        self,
        names: list[tuple[int, ...]],
        target: "Items",
        place: str,
        word: str,
    ) -> list[tuple[str, Item]] | str:
        """Transfer sibling items and descendants to a collection.

        The items go at the place in `target` (see `plan_place()`), in
        order.  Each item keeps the rest of its tag if it is free in
        `target`, or else gets a new one as `create` does; its
        `Details.md` and `Summary.md` headings are fixed, and the
        transfer is added to the "moves" list of its `.item.json`.  Both
        collections are renumbered to leave no gaps.  The plan is first
        written to `.transfer.json` (see `do_transfer()`), so that an
        interrupted transfer is finished the next time a collection is
        loaded.

        Arguments:
        * `names` (`list[tuple[int, ...]]`):
          The names of the sibling items to transfer.
        * `target` (`Items`):
          The collection to transfer them to, which has the same type.
        * `place` (`str`):
          "", "before" or "after".
        * `word` (`str`):
          The number or tag of the place in `target`.

        Returns:
        * (`list[tuple[str, Item]] | str`): Each transferred item with
          its old tag, or an error string on failure.
        """
        # Check the transfer.
        first: tuple[int, ...] | str = self.check_transfer(
            names, target, place, word
        )
        if isinstance(first, str):
            return first

        # Plan making room in the target.
        planned: (
            tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]
            | str
        ) = target.plan_place([], place, first, len(names))
        if isinstance(planned, str):  # pragma: no cover
            # `check_transfer()` checked the place.
            return planned

        # Find the new name of each item, with its descendants.
        target_names: dict[tuple[int, ...], tuple[int, ...]]
        first_name: tuple[int, ...]
        target_names, first_name = planned
        moving: list[tuple[Item, tuple[int, ...]]] = [
            (
                item,
                first_name[:-1]
                + (first_name[-1] + index,)
                + item.name[len(name) :],
            )
            for index, name in enumerate(names)
            for item in self.list_items(name)
        ]

        # Record each item's move, with a tag that is free in the
        # target.
        used: set[str] = {item.tag for item in target.items.values()}
        records: list[dict[str, str]] = []
        index: int
        item: Item
        new_name: tuple[int, ...]
        for index, (item, new_name) in enumerate(moving):
            tag: str = (
                item.tag
                if item.tag not in used
                else unique_tag(base_tag(item.title), used)
            )
            used.add(tag)
            old_directory: Path = self.directories[item.name]
            records.append(
                {
                    "old": old_directory.name,
                    "temporary": f".transfer_{index}",
                    "new": f"{number_text(new_name)}_"
                    f"{old_directory.name.partition('_')[2]}",
                    "old_number": item.number,
                    "new_number": number_text(new_name),
                    "tag": tag,
                    "old_tag": f"{self.prefix}{item.tag}",
                    "new_tag": f"{target.prefix}{tag}",
                    "title": item.title,
                    "summary": "yes" if target.has_file("Summary.md") else "",
                }
            )

        # Close the gaps that the items leave behind.
        moved: set[tuple[int, ...]] = {item.name for item, _ in moving}
        source_names: dict[tuple[int, ...], tuple[int, ...]] = (
            self.gap_free_names(
                name for name in self.items if name not in moved
            )
        )

        # Do the whole plan, which can be finished after a failure.
        stamp: str = utc_stamp(time.time())
        plan: dict[str, object] = {
            "target": target.items_directory.name,
            "time": stamp,
            "items": records,
            "source_renames": self.rename_records(source_names),
            "target_renames": target.rename_records(target_names),
        }
        error: str = do_transfer(self.items_directory, plan, 1)
        if error:
            return error

        # Move the items in memory and give the others their new names.
        for item, _ in moving:
            del self.items[item.name]
            del self.directories[item.name]
        self.apply_renames(source_names)
        target.apply_renames(target_names)

        # Update each transferred item.
        transferred: list[tuple[str, Item]] = []
        record: dict[str, str]
        for (item, new_name), record in zip(moving, records, strict=True):
            item.name = new_name
            item.tag = record["tag"]
            item.updated = stamp
            target.items[new_name] = item
            target.directories[new_name] = (
                target.items_directory / record["new"]
            )
            transferred.append((record["old_tag"], item))

        # Return each item with its old tag.
        return transferred

    # Method `Items.set_state()`:
    def set_state(
        self, name: tuple[int, ...], state: str, recursive: bool = False
    ) -> list[Item] | str:
        """Set the state of an item, and its descendants if recursive.

        An item already in `state` is left unchanged.  Otherwise its
        updated time is set to now and the change is added to its
        history.

        Arguments:
        * `name` (`tuple[int, ...]`):
          The item's name.
        * `state` (`str`):
          The new state.
        * `recursive` (`bool`):
          True to set the state of the item's descendants too.

        Returns:
        * (`list[Item] | str`): The selected items, or an error string
          on failure.
        """
        # The state must be one of the type's states.
        states: tuple[str, ...] = self.collection_type.states
        if state not in states:
            return f"State '{state}' is not one of {', '.join(states)}"

        # Select the items.
        changed: list[Item] | str = self.select_items(name, recursive)
        if isinstance(changed, str):
            return changed

        # An Active rule needs a copy of its source.
        if self.collection_type.has_sources and state == "Active":
            item: Item
            for item in changed:
                if not item.source or not self.copy_path(item).is_file():
                    tag: str = f"{self.prefix}{item.tag}"
                    return (
                        f"{tag} has no copy of a source to make Active; "
                        f"`ai_contexts {tag} source PATH` sets its source"
                    )

        # Change the state of each item that is not already in it.
        for item in changed:
            if item.state == state:
                continue
            item_directory: Path = self.directories[item.name]
            try:
                item.updated = update_item(item_directory, state)
            except (OSError, ValueError) as error:
                item_path: Path = item_directory / ITEM_FILE
                return f"Unable to write '{item_path}': {error}"
            item.state = state

        # Return the selected items.
        return changed

    # Method `Items.set_priority()`:
    def set_priority(
        self, name: tuple[int, ...], priority: int | None
    ) -> Item | str:
        """Set or remove the priority of an item.

        The updated time is set to now.

        Arguments:
        * `name` (`tuple[int, ...]`):
          The item's name.
        * `priority` (`int | None`):
          The new priority, or `None` to remove it.

        Returns:
        * (`Item | str`): The item, or an error string on failure.
        """
        # Select the item.
        selected: list[Item] | str = self.select_items(name)
        if isinstance(selected, str):
            return selected
        item: Item = selected[0]

        # Write the priority.
        item_directory: Path = self.directories[name]
        try:
            item.updated = update_item(
                item_directory, fields={"priority": priority}
            )
        except (OSError, ValueError) as error:
            return f"Unable to write '{item_directory / ITEM_FILE}': {error}"

        # Keep it in memory once it is written.
        item.priority = priority
        return item

    # Method `Items.feature_command()`:
    def feature_command(self, command: str, arguments: list[str]) -> str:
        """Run `enable FEATURE` or `disable FEATURE`.

        FEATURE may be any unique prefix of a feature.

        Arguments:
        * `command` (`str`):
          "enable" or "disable".
        * `arguments` (`list[str]`):
          The command's arguments.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Find the one feature.
        found: list[str] = matches(arguments[0], FEATURES) if arguments else []
        if len(arguments) != 1 or len(found) != 1:
            return (
                f"Usage: ai_contexts COLLECTION {command} FEATURE, where "
                f"FEATURE is one of: {', '.join(FEATURES)}"
            )

        # Enable or disable it.
        return self.set_feature(found[0], command == "enable")

    # Method `Items.set_source()`:
    def set_source(self, name: tuple[int, ...], path: Path) -> Item | str:
        """Make a file the source of a rule, and copy it.

        The source is kept relative to `root`, after the directories in
        `path` are resolved to real ones; the file name is kept, so a
        file that is a symbolic link is followed whenever it is read.  A
        copy of the old source is removed, and the copy is always
        replaced.

        Arguments:
        * `name` (`tuple[int, ...]`):
          The rule's name.
        * `path` (`Path`):
          The source file.

        Returns:
        * (`Item | str`): The rule, or an error string on failure.
        """
        # Select the rule; the file must be a file.  Its name was
        # checked by `screen_sources()`.
        selected: list[Item] | str = self.select_items(name)
        if isinstance(selected, str):
            return selected
        item: Item = selected[0]
        if not path.is_file():
            return f"'{path.as_posix()}' is not a file"

        # Keep the source relative to the root, with real directories.
        source: str = (
            Path(os.path.relpath(path.absolute().parent.resolve(), self.root))
            .joinpath(path.name)
            .as_posix()
        )

        # Remove the old copy and record the new source.
        item_directory: Path = self.directories[name]
        try:
            if item.source:
                remove_file(self.copy_path(item))
            item.updated = update_item(
                item_directory,
                fields={"source": source, "sha256": None, "refreshed": None},
            )
        except (OSError, ValueError) as error:
            return (
                f"Unable to set the source of {self.prefix}{item.tag}: {error}"
            )

        # Copy the new source.
        item.source = source
        message: str = self.refresh_rule(item, force=True)
        if message.startswith("Unable"):
            return message
        return item

    # Method `Items.source_command()`:
    def source_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `source NUMBER PATH`: set and copy the source of a rule.

        A file that does not look like a rule is only used if the user
        answers yes (see `screen_sources()`).

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        if len(arguments) != 2:
            return "Usage: ai_contexts COLLECTION source NUMBER PATH"
        name: tuple[int, ...] | str = self.resolve(arguments[0])
        if isinstance(name, str):
            return name
        paths: list[Path] | str = (
            screen_sources([Path(arguments[1])], ask)
            if Path(arguments[1]).is_file()
            else [Path(arguments[1])]
        )
        if isinstance(paths, str):
            return paths
        changed: Item | str = self.set_source(name, paths[0])
        if isinstance(changed, str):
            return changed
        self.show([changed])
        return ""

    # Method `Items.refresh_command()`:
    def refresh_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `refresh NUMBER`: copy a rule's source over its copy.

        A copy that was edited in place is only replaced if the user
        answers yes.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        if len(arguments) != 1:
            return "Usage: ai_contexts COLLECTION refresh NUMBER"
        name: tuple[int, ...] | str = self.resolve(arguments[0])
        if isinstance(name, str):
            return name
        selected: list[Item] | str = self.select_items(name)
        if isinstance(selected, str):
            return selected
        item: Item = selected[0]
        tag: str = f"{self.prefix}{item.tag}"
        if not item.source:
            return (
                f"{tag} has no source; `ai_contexts {tag} source PATH` "
                "sets one"
            )
        message: str = self.refresh_rule(item)
        if "edited in place" in message:
            try:
                answer: str = ask(
                    f"Replace the edited copy of {tag} with its source "
                    f"'{item.source}'? (y=Yes, n=No) "
                )
            except EOFError:
                answer = ""
            if answer.strip().casefold() not in ("y", "yes"):
                return "Not refreshed"
            message = self.refresh_rule(item, force=True)
        if message.startswith(("Unable", tag)):
            return message
        print(message or f"{tag} is up to date")
        return ""

    # Method `Items.create_rules()`:
    def create_rules(
        self,
        place: str,
        word: str,
        paths: list[Path],
        titles: dict[Path, str] | None = None,
    ) -> list[Item] | str:
        """Create a rule from each of some files, at a place.

        The first rule goes at `word` (see `plan_place()`), and each of
        the others after the one before.  Each is titled from `titles`,
        or else from its file name, and has its source set.  The rules
        are printed.

        Arguments:
        * `place` (`str`):
          "", "before" or "after".
        * `word` (`str`):
          A number, or with `place`, a number or tag.
        * `paths` (`list[Path]`):
          The source files.
        * `titles` (`dict[Path, str] | None`):
          The title of each source file, if not its name.

        Returns:
        * (`list[Item] | str`): The new rules, or an error string on
          failure.
        """
        # Create each rule after the one before, and set its source.
        created: list[Item] = []
        path: Path
        for path in paths:
            title: str = (titles or {}).get(path) or path.stem.replace(
                "_", " "
            )
            item: Item | str = (
                self.create_item(created[-1].number, title, "after")
                if created
                else self.create_item(word, title, place)
            )
            if isinstance(item, str):
                return item
            created.append(item)
            sourced: Item | str = self.set_source(item.name, path)
            if isinstance(sourced, str):
                return sourced

        # Print the new rules.
        self.show(created)
        return created

    # Method `Items.copy_command()`:
    def copy_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `copy DIRECTORY [CHOICES...]`: copy rules from elsewhere.

        The rules in DIRECTORY (another project's rules collection, or a
        directory of rule files; see `offered_rules()`) are listed by
        number and title, marking those already here (the same source,
        or the same text).  The CHOICES (see `parse_choices()`) are
        asked for if not given.  The chosen rules, less those already
        here, are screened (see `screen_sources()`) and created after
        the last rule, InActive, with their files as their sources.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Find the rules offered by the directory.
        if not arguments:
            return "Usage: ai_contexts COLLECTION copy DIRECTORY [CHOICES...]"
        directory: Path = Path(arguments[0])
        if not directory.is_dir():
            return f"'{directory.as_posix()}' is not a directory"
        offered: list[tuple[str, Path]] = offered_rules(directory)
        if not offered:
            return f"'{directory.as_posix()}' has no rules to copy"

        # Note the sources and texts of the rules already here.
        sources: set[Path] = set()
        hashes: set[str] = set()
        item: Item
        for item in self.list_items():
            with contextlib.suppress(OSError):
                if item.source:
                    sources.add((self.root / item.source).resolve())
                if self.copy_path(item).is_file():
                    hashes.add(sha256_of(self.copy_path(item)))
        have: list[bool] = []
        title: str
        path: Path
        for title, path in offered:
            try:
                have.append(
                    path.resolve() in sources or sha256_of(path) in hashes
                )
            except OSError:
                have.append(False)

        # List them, and get the choices.
        width: int = len(str(len(offered)))
        print(f"Rules in {directory.as_posix()}:")
        number: int
        for number, (title, path) in enumerate(offered, 1):
            mark: str = "  (have it)" if have[number - 1] else ""
            print(f"{number:>{width}}  {title}{mark}")
        text: str = " ".join(arguments[1:])
        if len(arguments) == 1:
            try:
                text = ask("Copy which? (e.g. 1,3-5; empty for none) ")
            except EOFError:
                text = ""
        chosen: list[int] | str = parse_choices(text, len(offered))
        if isinstance(chosen, str):
            return chosen

        # Leave out the rules already here.
        for number in chosen:
            if have[number - 1]:
                print(f"Already have {number}  {offered[number - 1][0]}")
        paths: list[Path] = [
            offered[number - 1][1] for number in chosen if not have[number - 1]
        ]
        if not paths:
            print("Nothing copied")
            return ""

        # Screen them, then create them after the last rule.
        screened: list[Path] | str = screen_sources(paths, ask)
        if isinstance(screened, str):
            return screened
        top: list[int] = [name[0] for name in self.items if len(name) == 1]
        created: list[Item] | str = self.create_rules(
            "",
            str(max(top, default=0) + 1),
            screened,
            {path: title for title, path in offered},
        )
        if isinstance(created, str):
            return created
        # Say how to use them: they are siblings, so one range.
        which: str = (
            f"{self.prefix}{created[0].tag}"
            if len(created) == 1
            else f"{created[0].number}-{created[-1].number}"
        )
        print(
            f"To use them: ai_contexts {self.items_directory.name} "
            f"activate {which}"
        )
        return ""

    # Method `Items.type_command()`:
    def type_command(self, arguments: list[str]) -> str:
        """Run `type [TYPE]`: print or set the type of the collection.

        TYPE may be any unique prefix of a type.  The type can only be
        changed while the collection is empty, so that no item is left
        in a state that its type does not have.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Find the type, if one is given.
        found: list[str] = matches(arguments[0], TYPES) if arguments else []
        if len(arguments) > 1 or (arguments and len(found) != 1):
            return (
                "Usage: ai_contexts COLLECTION type [TYPE], where TYPE is one "
                f"of: {', '.join(TYPES)}"
            )

        # Change the type, but only while there are no items.
        name: str = self.items_directory.name
        if found and found[0] != self.collection_type_name:
            if self.items:
                return (
                    f"The type of '{name}' can only be changed while it has "
                    "no items"
                )
            error: str = self.save_settings(
                {**self.settings, "type": found[0]}
            )
            if error:
                return error

        # Print the type.
        print(f"{name}: {self.collection_type_name}")
        return ""

    # Method `Items.priority_command()`:
    def priority_command(self, arguments: list[str]) -> str:
        """Run `priority NUMBER LEVEL`.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Priority must be enabled.
        if not self.priority_enabled:
            name: str = self.items_directory.name
            return (
                f"Priority is not enabled for '{name}'; use "
                f"`ai_contexts {name} enable priority`"
            )

        # Parse the arguments.
        if len(arguments) != 2:
            return "Usage: ai_contexts COLLECTION priority NUMBER LEVEL"
        number: tuple[int, ...] | str = self.resolve(arguments[0])
        if isinstance(number, str):
            return number
        priority: int | None | str = parse_priority(arguments[1])
        if isinstance(priority, str):
            return priority

        # Set the priority and print the item.
        changed: Item | str = self.set_priority(number, priority)
        if isinstance(changed, str):
            return changed
        self.show([changed])
        return ""

    # Method `Items.create_command()`:
    def create_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `create [before|after] NUMBER TITLE...`.

        In a collection with sources it is `create [before|after] NUMBER
        FILE...` (see `create_rules()`), and files that do not look like
        rules are only used if the user answers yes (see
        `screen_sources()`).

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Parse the arguments.
        place: str = ""
        if arguments and arguments[0] in PLACES:
            place, arguments = arguments[0], arguments[1:]
        sources: bool = self.collection_type.has_sources
        if len(arguments) < 2:
            return (
                "Usage: ai_contexts COLLECTION create [before|after] NUMBER "
                + ("FILE..." if sources else "TITLE...")
            )

        # A rules collection makes a rule from each file.
        if sources:
            paths: list[Path] | str = expand_files(arguments[1:])
            if isinstance(paths, str):
                return paths
            paths = screen_sources(paths, ask)
            if isinstance(paths, str):
                return paths
            rules: list[Item] | str = self.create_rules(
                place, arguments[0], paths
            )
            return rules if isinstance(rules, str) else ""

        # Otherwise make an item with the title.
        result: Item | str = self.create_item(
            arguments[0], " ".join(arguments[1:]), place
        )
        return result if isinstance(result, str) else ""

    # Method `Items.move_command()`:
    def move_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `move NUMBER [before|after] NUMBER`.

        A valid move may first ask to continue (see
        `confirm_snapshot()`).  The renumbered items are printed.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Parse the arguments.
        place: str = ""
        if len(arguments) == 3 and arguments[1] in PLACES:
            place = arguments[1]
        elif len(arguments) != 2:
            return (
                "Usage: ai_contexts COLLECTION move NUMBER [before|after] "
                "NUMBER"
            )
        names: list[tuple[int, ...]] | str = self.resolve_range(arguments[0])
        if isinstance(names, str):
            return names

        # Resolve the place and plan the move, which must be valid.
        target: tuple[int, ...] | str = (
            self.resolve(arguments[-1])
            if place
            else parse_number(arguments[-1])
        )
        if isinstance(target, str):
            return target
        planned: (
            tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]
            | str
        ) = self.plan_place(names, place, target)
        if isinstance(planned, str):
            return planned

        # Ask about a snapshot, then move the items.
        if not self.confirm_snapshot(ask):
            return "Not moved"
        renumbered: dict[str, Item] | str = self.move_items(
            names, place, target
        )
        if isinstance(renumbered, str):
            return renumbered

        # Note the time of the move.
        error: str = self.note_move_or_rename()
        if error:
            return error

        # Print the renumbered items.
        if not renumbered:
            print("Nothing moved")
        self.show_renumbered(renumbered)
        return ""

    # Method `Items.transfer_command()`:
    def transfer_command(
        self,
        arguments: list[str],
        collections: list["Items"],
        ask: Callable[[str], str] = input,
    ) -> str:
        """Run `transfer NUMBER COLLECTION [[before|after] NUMBER]`.

        COLLECTION is one of `collections`, by any unique prefix.
        Without a place, the items go to the next free top-level number.
        A valid transfer may first ask to continue (see
        `confirm_snapshot()`).  The transferred items and the renumbered
        ones are printed, then the user is offered a change of their old
        tags in the project's `.md` files (see `update_references()`),
        which drops each old tag's `~NUMBER`, since the number was in
        the other collection.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.
        * `collections` (`list[Items]`):
          Every collection.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Parse the arguments.
        usage: str = (
            "Usage: ai_contexts COLLECTION transfer NUMBER COLLECTION "
            "[[before|after] NUMBER]"
        )
        place: str = ""
        if len(arguments) == 4 and arguments[2] in PLACES:
            place = arguments[2]
        elif len(arguments) not in (2, 3):
            return usage
        names: list[tuple[int, ...]] | str = self.resolve_range(arguments[0])
        if isinstance(names, str):
            return names

        # Find the target collection, which must be loaded.
        found: list[str] = matches(
            arguments[1],
            [collection.items_directory.name for collection in collections],
        )
        if len(found) != 1:
            return (
                f"'{arguments[1]}' does not match one collection: "
                + ", ".join(
                    collection.items_directory.name
                    for collection in collections
                )
            )
        target: Items = next(
            collection
            for collection in collections
            if collection.items_directory.name == found[0]
        )
        if target.error:
            return f"Collection '{found[0]}' can not be loaded"

        # The place defaults to the next free top-level number.
        word: str = (
            arguments[-1]
            if len(arguments) > 2
            else str(sum(1 for name in target.items if len(name) == 1) + 1)
        )
        checked: tuple[int, ...] | str = self.check_transfer(
            names, target, place, word
        )
        if isinstance(checked, str):
            return checked

        # Ask about a snapshot, noting each item's number before.
        if not self.confirm_snapshot(ask):
            return "Not transferred"
        before: dict[int, tuple[str, Item]] = {
            id(item): (item.number, item)
            for collection in (self, target)
            for item in collection.items.values()
        }

        # Transfer the items and note the time.
        transferred: list[tuple[str, Item]] | str = self.transfer_items(
            names, target, place, word
        )
        if isinstance(transferred, str):
            return transferred
        error: str = self.note_move_or_rename() or target.note_move_or_rename()
        if error:
            return error

        # Print the transferred items.
        print("Transferred (old tag first):")
        target.show(
            [item for _, item in transferred],
            old_numbers=[old_tag for old_tag, _ in transferred],
        )

        # Print the renumbered items of each collection.
        moved: set[int] = {id(item) for _, item in transferred}
        collection: Items
        for collection in (self, target):
            renumbered: dict[str, Item] = {
                before[id(item)][0]: item
                for item in collection.list_items()
                if id(item) not in moved and before[id(item)][0] != item.number
            }
            if renumbered:
                print(f"In {collection.items_directory.name}:")
                collection.show_renumbered(renumbered)

        # Offer to update the old tags in the project's `.md` files.
        return self.update_references(
            {
                old_tag: f"{target.prefix}{item.tag}"
                for old_tag, item in transferred
            },
            ask,
            drop_numbers=True,
        )

    # Method `Items.show_command()`:
    def show_command(self, arguments: list[str]) -> str:
        """Run `show NUMBER`: print everything about an item.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Find the item.
        if len(arguments) != 1:
            return "Usage: ai_contexts COLLECTION show NUMBER"
        name: tuple[int, ...] | str = self.resolve(arguments[0])
        if isinstance(name, str):
            return name
        if name not in self.items:
            return f"Item '{number_text(name)}' does not exist"

        # Read its metadata and `Details.md` (which a rule may not have
        # until its source is copied).
        item: Item = self.items[name]
        item_directory: Path = self.directories[name]
        details_path: Path = item_directory / "Details.md"
        try:
            metadata: dict[str, object] = read_item(item_directory)
            details: str = (
                read_file(details_path)
                if details_path.exists()
                or not self.collection_type.has_sources
                else ""
            )
        except (OSError, ValueError) as error:
            return f"Unable to read item '{item.number}': {error}"

        # Print its details.
        lines: list[str] = [
            f"Number:    {item.number}",
            f"Tag:       {self.prefix}{item.tag}",
            f"Title:     {item.title}",
            f"State:     {item.state}",
        ]
        if self.priority_enabled:
            lines.append(
                f"Priority:  {'-' if item.priority is None else item.priority}"
            )

        # A rule also has its source, hash and refresh time.
        if self.collection_type.has_sources:
            lines += [
                f"Source:    {item.source or '-'}",
                f"SHA-256:   {metadata.get('sha256', '-')}",
                (
                    "Refreshed: "
                    f"{local_time(str(metadata.get('refreshed', '')))}"
                ),
            ]

        # Then come the times, the directory and the state history.
        lines += [
            f"Created:   {local_time(item.created)}",
            f"Updated:   {local_time(item.updated)}",
            f"Directory: {item_directory.parent.name}/{item_directory.name}",
            "History:",
        ]
        history: object = metadata.get("history")
        change: object
        for change in history if isinstance(history, list) else []:
            if isinstance(change, dict):
                lines.append(
                    f"  {local_time(str(change.get('time', ''))):<16}  "
                    f"{change.get('state', '?')}"
                )

        # Then any transfers.
        moves: object = metadata.get("moves")
        if isinstance(moves, list) and moves:
            lines.append("Transfers:")
            lines += [
                f"  {local_time(str(move.get('time', ''))):<16}  "
                f"{move.get('from', '?')} -> {move.get('to', '?')}"
                for move in moves
                if isinstance(move, dict)
            ]

        # Print the details, then `Details.md`.
        print("\n".join(lines) + "\n")
        print(details, end="")
        return ""

    # Method `Items.show_renumbered()`:
    def show_renumbered(self, renumbered: dict[str, Item]) -> None:
        """Print the renumbered items, with their old numbers.

        Arguments:
        * `renumbered` (`dict[str, Item]`):
          The renumbered items, keyed by their old numbers.
        """
        # There is nothing to print without renumbered items.
        if renumbered:
            print("Renumbered (old number first):")
            self.show(list(renumbered.values()), old_numbers=list(renumbered))

    # Method `Items.list_command()`:
    def list_command(self, arguments: list[str]) -> str:
        """Run `list [-a] [-l] [NUMBER]`.

        Closed and Rejected items are left out, unless `-a` is given or
        it is the item NUMBER itself, and a note says how many.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Separate the options from the number.
        long: bool = False
        everything: bool = False
        numbers: list[str] = []
        argument: str
        for argument in arguments:
            if argument in ("-l", "--long"):
                long = True
            elif argument in ("-a", "--all"):
                everything = True
            else:
                numbers.append(argument)

        # There may be at most one number or tag.
        if len(numbers) > 1:
            return "Usage: ai_contexts COLLECTION list [-a] [-l] [NUMBER]"
        name: tuple[int, ...] | str = (
            self.resolve(numbers[0]) if numbers else ()
        )
        if isinstance(name, str):
            return name

        # Leave out finished items, unless asked for, and count them.
        listed: list[Item] = self.list_items(name)
        hidden: int = 0
        if not everything:
            shown: list[Item] = [
                item
                for item in listed
                if item.state not in self.collection_type.finished_states
                or item.name == name
            ]
            hidden = len(listed) - len(shown)
            listed = shown

        # With priority enabled, list by priority first.
        if self.priority_enabled:
            listed.sort(
                key=lambda item: (
                    item.priority is None,
                    item.priority or 0,
                    item.name,
                )
            )

        # Print the items and how many were left out.
        self.show(listed, long)
        if hidden:
            print(
                f"({hidden} Closed or Rejected item"
                f"{'' if hidden == 1 else 's'} not "
                "shown; `ls -a` shows them)"
            )
        return ""

    # Method `Items.state_command()`:
    def state_command(self, command: str, arguments: list[str]) -> str:
        """Run a state command, like `open`, with `[-r] NUMBER`.

        NUMBER may be a range of siblings, like 1.2.5-6.

        Arguments:
        * `command` (`str`):
          The state command.
        * `arguments` (`list[str]`):
          The command's arguments.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Parse the arguments.
        parsed: tuple[list[tuple[int, ...]], bool] | str = parse_recursive(
            command, arguments, self.resolve_range
        )
        if isinstance(parsed, str):
            return parsed
        names: list[tuple[int, ...]]
        recursive: bool
        names, recursive = parsed

        # Set the state of each item and print the items.
        shown: list[Item] = []
        name: tuple[int, ...]
        for name in names:
            changed: list[Item] | str = self.set_state(
                name, STATE_COMMANDS[command], recursive
            )
            if isinstance(changed, str):
                return changed
            shown += changed
        self.show(shown)
        return ""

    # Method `Items.rename_command()`:
    def rename_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `rename NUMBER to TITLE...`.

        A rename of an existing item to a usable title may first ask to
        continue (see `confirm_snapshot()`).

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Parse the arguments; the item must exist and have a title.
        if len(arguments) < 3 or arguments[1] != "to":
            return "Usage: ai_contexts COLLECTION rename NUMBER to TITLE..."
        name: tuple[int, ...] | str = self.resolve(arguments[0])
        if isinstance(name, str):
            return name
        if name not in self.items:
            return f"Item '{number_text(name)}' does not exist"
        title: str = " ".join(arguments[2:])
        if not clean_title(title):
            return f"Item '{number_text(name)}' has an empty title"

        # Ask about a snapshot, then rename the item.
        if not self.confirm_snapshot(ask):
            return "Not renamed"
        old_tag: str = f"{self.prefix}{self.items[name].tag}"
        renamed: Item | str = self.rename_item(name, title)
        if isinstance(renamed, str):
            return renamed

        # Note the time of the rename and print the item.
        error: str = self.note_move_or_rename()
        if error:
            return error
        self.show([renamed])

        # Offer to update the old tag if it changed.
        new_tag: str = f"{self.prefix}{renamed.tag}"
        if new_tag == old_tag:
            return ""
        return self.update_references({old_tag: new_tag}, ask)

    # Method `Items.update_references()`:
    def update_references(
        self,
        tags: dict[str, str],
        ask: Callable[[str], str],
        drop_numbers: bool = False,
    ) -> str:
        """Offer to change old tags to new ones in the `.md` files.

        The files are found by `tag_references()` in the collections and
        directly in the directory that holds them, and every old tag is
        changed in one pass if the user answers yes.  Since nothing else
        is searched, a hint says how to look for the old tags elsewhere.

        Arguments:
        * `tags` (`dict[str, str]`):
          The new tag of each old tag.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.
        * `drop_numbers` (`bool`):
          True to also remove the `~NUMBER` after an old tag (e.g.
          "T.fbm~12" becomes "I.fbm"), for a transfer, where the
          number belonged to the old collection.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Find the files that use the old tags.
        root: Path = self.items_directory.parent
        paths: list[Path] = sorted(
            {
                path
                for old_tag in tags
                for path in tag_references(root, old_tag)
            },
            key=Path.as_posix,
        )
        print(
            "Only the collections and the `.md` files directly in "
            f"'{root}' are searched for old tags; to look elsewhere, use "
            "e.g. `grep -rnwF -e " + " -e ".join(tags) + " .`"
        )
        if not paths:
            return ""

        # List them and ask whether to update them.
        print("The following `.md` files have tags that need to be renamed:")
        path: Path
        for path in paths:
            print(f"  {path.relative_to(root).as_posix()}")
        try:
            answer: str = ask("OK to update them? (y=Yes, n=No) ")
        except EOFError:
            answer = ""
        if answer.strip().casefold() not in ("y", "yes"):
            print(
                f"Not updated; {', '.join(tags)} "
                f"{'is' if len(tags) == 1 else 'are'} still used in them"
            )
            return ""

        # One pattern changes every tag at once, so that a new tag is
        # never changed again as another's old tag.
        pattern: re.Pattern[str] = re.compile(
            "("
            + "|".join(tag_pattern(old_tag).pattern for old_tag in tags)
            + ")"
            + (r"(?:~\d+(?:\.\d+)*)?" if drop_numbers else "")
        )
        for path in paths:
            try:
                write_file(
                    path,
                    pattern.sub(
                        lambda found: tags[found.group(1)], read_file(path)
                    ),
                )
            except OSError as error:
                return f"Unable to update '{path}': {error}"

        # Report the update.
        print(
            "Updated "
            + ", ".join(f"{old} to {new}" for old, new in tags.items())
            + f" in {len(paths)} files"
        )
        return ""

    # Method `Items.delete_command()`:
    def delete_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `delete [-r] NUMBER`, where NUMBER may be a range.

        The deleted items and the renumbered ones are printed.

        Arguments:
        * `arguments` (`list[str]`):
          The command's arguments.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`str`): An empty string on success, or an error string on
          failure.
        """
        # Separate the `-r` option from the number or range.
        recursive: bool = False
        words: list[str] = []
        argument: str
        for argument in arguments:
            if argument in ("-r", "--recursive"):
                recursive = True
            else:
                words.append(argument)

        # There must be exactly one number or range.
        if len(words) != 1:
            return "Usage: ai_contexts COLLECTION delete [-r] NUMBER"
        names: list[tuple[int, ...]] | str = self.resolve_range(words[0])
        if isinstance(names, str):
            return names

        # Delete the items.
        result: tuple[list[Item], dict[str, Item]] | str = self.delete_items(
            names, recursive, ask
        )
        if isinstance(result, str):
            return result

        # Print the deleted and renumbered items.
        deleted: list[Item]
        renumbered: dict[str, Item]
        deleted, renumbered = result
        print("Deleted:")
        self.show(deleted)
        self.show_renumbered(renumbered)
        return ""

    # Method `Items.create_collection()`:
    @staticmethod
    def create_collection(
        name: str, directories: list[Path], ask: Callable[[str], str]
    ) -> int:
        """Run `NAME create` to create a collection directory.

        It goes next to the existing collections, or else in the current
        directory, if the user answers yes.

        Arguments:
        * `name` (`str`):
          The name of the new collection, exactly as typed.
        * `directories` (`list[Path]`):
          The existing collections.
        * `ask` (`Callable[[str], str]`):
          Asks the user a question and returns the answer.

        Returns:
        * (`int`): 0 for success and 1 for failure.
        """
        # The name must be a plain directory name.
        if name in ("", ".", "..") or Path(name).name != name:
            print(f"Invalid collection name '{name}'", file=sys.stderr)
            return 1

        # The collection must not exist yet.
        parent: Path = directories[0].parent if directories else Path.cwd()
        path: Path = parent / name
        if path.exists():
            print(f"'{path}' already exists", file=sys.stderr)
            return 1

        # Its tag prefix must be unused.
        prefix: str = tag_prefix(name)
        clashes: list[str] = [
            directory.name
            for directory in directories
            if tag_prefix(directory.name) == prefix
        ]
        if clashes:
            print(
                f"Collection '{name}' would have the tag prefix '{prefix}', "
                f"which '{clashes[0]}' already has",
                file=sys.stderr,
            )
            return 1

        # Ask before creating it.
        try:
            answer: str = ask(f"Create collection directory '{path}'? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().casefold() not in ("y", "yes"):
            print("Not created", file=sys.stderr)
            return 1

        # Create it; one named RULES (in any case) is a rules collection.
        created: Items = Items(path)
        if created.error:
            return 1
        error: str = ""
        if name.casefold() == "rules":
            error = created.save_settings(
                {**created.settings, "type": "rules"}
            )
            if error:
                print(error, file=sys.stderr)
                return 1
            print(f"Created '{path}', a rules collection")
        else:
            print(f"Created '{path}'")

        # Rewrite `Startup.md` to include it, and write the rules files.
        collections: list[Items] = [
            Items(directory) for directory in directories
        ]
        loaded: list[Items] = [
            collection
            for collection in [created, *collections]
            if not collection.error
        ]
        error = write_startup(loaded) or write_rules_files(loaded)
        if error:
            print(error, file=sys.stderr)
            return 1
        return 0

    # Method `Items.list_collections()`:
    @staticmethod
    def list_collections() -> int:
        """Run `ai_contexts` with no arguments: list the collections.

        Prints how many collections were found and where, a numbered
        line for each with its tag prefix and how many items it has in
        each state, and a pointer to the help.

        Returns:
        * (`int`): 0.
        """
        # Find the collections and say where they are.
        directories: list[Path] = find_collections(Path.cwd())
        where: str = f" in '{directories[0].parent}'" if directories else ""
        print(
            f"{len(directories)} collection"
            f"{'' if len(directories) == 1 else 's'} found{where}"
            f"{':' if directories else ''}"
        )

        # List each one with its items' states.
        width: int = max((len(path.name) for path in directories), default=0)
        number_width: int = len(str(len(directories)))
        number: int
        directory: Path
        for number, directory in enumerate(directories, 1):
            items: Items = Items(directory)
            states: list[str] = [item.state for item in items.items.values()]
            counts: list[str] = [
                f"{states.count(state)} {state}"
                for state in ALL_STATES
                if state in states
            ]
            total: int = len(items.items)
            print(
                f"{number:>{number_width}} - {directory.name:<{width}}  "
                f"{items.prefix}  "
                + (
                    f"{total} item{'' if total == 1 else 's'}: "
                    + ", ".join(counts)
                    if total
                    else "no items"
                )
            )

        # Point to how to create one, and to the help.
        if not directories:
            print("`ai_contexts NAME create` creates one.")
        print("Type: `ai_contexts -h` for more help.")
        return 0

    # Method `Items.run_command()`:
    @staticmethod
    def run_command(
        arguments: list[str], ask: Callable[[str], str] = input
    ) -> int:
        """Run an ai_contexts command.

        Arguments:
        * `arguments` (`list[str]`):
          The command line arguments, without the program name.
        * `ask` (`Callable[[str], str]`):
          Asks the user a yes/no question, like whether to create a new
          collection, and returns the answer.

        Returns:
        * (`int`): 0 for success and 1 for failure.
        """
        # Handle no arguments, the help, the version and the tests.
        if not arguments:
            return Items.list_collections()
        if arguments[0] in ("-h", "--help"):
            print(HELP)
            return 0
        if arguments == ["--version"]:
            print(f"aicontexts {__version__}")
            return 0
        if arguments == ["--test"]:  # pragma: no cover
            # The tests are in `ai_contexts_test.py`, next to this file
            # (even when ai_contexts is run through a symbolic link).
            # They are not run from here when coverage is measured,
            # which runs `ai_contexts_test.py` itself.  They are only
            # imported here, so that a normal run does not load them,
            # and they import this module, which `pylint` reports as a
            # cyclic import.
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            # pylint: disable-next=import-outside-toplevel,cyclic-import
            import ai_contexts_test

            return ai_contexts_test.test()

        # Find the collection, or the collection of a tag.
        error: str = ""
        directories: list[Path] = find_collections(Path.cwd())
        names: list[str] = [directory.name for directory in directories]
        found: list[str] = matches(arguments[0], names)
        tag: str = ""
        if not found and tag_collection(arguments[0], names):
            found = [tag_collection(arguments[0], names)]
            tag = arguments[0]

        # A collection's type decides its commands; when there is no
        # such collection, every command is allowed (for `ai_contexts
        # NAME create`).
        known: dict[str, str] = commands(
            type_name(directories[names.index(found[0])])
            if len(found) == 1
            else ""
        )
        matched: list[str] = (
            sorted({known[name] for name in matches(arguments[1], known)})
            if len(arguments) > 1
            else []
        )

        # Check the arguments, or create a new collection.
        if arguments[0].startswith("-"):
            error = f"Unknown option '{arguments[0]}'\n{HELP}"
        elif len(found) > 1:
            error = (
                f"'{arguments[0]}' matches more than one collection: "
                f"{', '.join(found)}"
            )
        elif len(arguments) < 2:
            error = "Usage: ai_contexts COLLECTION COMMAND [ARGUMENTS...]"
        elif not matched:
            error = other_type_error(
                arguments[1],
                found[0] if len(found) == 1 else "",
                directories[names.index(found[0])]
                if len(found) == 1
                else None,
            ) or (
                f"Unknown command '{arguments[1]}'; the commands are: "
                f"{', '.join(known)}"
            )
        elif len(matched) > 1:
            error = (
                f"'{arguments[1]}' matches more than one command: "
                f"{', '.join(matched)}"
            )
        elif tag and matched[0] not in TAG_COMMANDS:
            error = f"A tag can not be used with '{matched[0]}'"
        elif not found and matched == ["create"] and len(arguments) == 2:
            return Items.create_collection(arguments[0], directories, ask)
        elif not found:
            error = f"No collection matches '{arguments[0]}'"
            if names:
                error += f"; the collections are: {', '.join(names)}"
            error += "\nUse `ai_contexts NAME create` to create one."

        # Report an error.
        if error:
            print(error, file=sys.stderr)
            return 1

        # Load every collection.
        collections: list[Items] = [
            Items(directory) for directory in directories
        ]
        items: Items = collections[names.index(found[0])]
        if items.error:
            return 1

        # Run the command, with any tag as its first argument.
        rest: list[str] = ([tag] if tag else []) + arguments[2:]
        match matched[0]:
            case "help":
                print(HELP)
            case "create":
                error = items.create_command(rest, ask)
            case "list":
                error = items.list_command(rest)
            case "rename":
                error = items.rename_command(rest, ask)
            case "delete":
                error = items.delete_command(rest, ask)
            case "priority":
                error = items.priority_command(rest)
            case "move":
                error = items.move_command(rest, ask)
            case "transfer":
                error = items.transfer_command(rest, collections, ask)
            case "show":
                error = items.show_command(rest)
            case "type":
                error = items.type_command(rest)
            case "source":
                error = items.source_command(rest, ask)
            case "refresh":
                error = items.refresh_command(rest, ask)
            case "copy":
                error = items.copy_command(rest, ask)
            case "enable" | "disable":
                error = items.feature_command(matched[0], rest)
            case state_command:
                error = items.state_command(state_command, rest)

        # After a success, rewrite `Startup.md`, `Active_Rules.md` and
        # the rules files.
        if not error:
            loaded: list[Items] = [
                collection
                for collection in collections
                if not collection.error
            ]
            error = (
                write_startup(loaded)
                or write_active_rules(loaded)
                or write_rules_files(loaded)
            )

        # Report any `CLAUDE.md` import of a missing file, then any
        # error.
        check_claude_imports(directories[0].parent)
        if error:
            print(error, file=sys.stderr)
            return 1
        return 0


# Function `write_startup()`:
def write_startup(collections: list["Items"]) -> str:
    """Write `Startup.md` (and `Closed.md`) into the TASKS collection.

    Nothing is written if there is no TASKS collection.  Every line of
    `Startup.md` is an `@` import, relative to the TASKS collection, so
    that adding `@TASKS/Startup.md` to `CLAUDE.md` loads them: the
    `Details.md` of every item that is not Closed and the `Context.md`
    of every Open or Reference item (the TASKS items first, then those
    of the other `collections` in order), then the `Summary.md` (or
    `Details.md` if the summary is empty) of the `CLOSED_SUMMARIES` (or
    the number in the `SUMMARIES_VARIABLE` environment variable) most
    recently Closed items, newest first, and finally `Closed.md` if
    there are older Closed items (see `write_closed()`).

    Arguments:
    * `collections` (`list[Items]`):
      Every collection.

    Returns:
    * (`str`): An empty string on success, or an error string on
      failure.
    """
    # Nothing is written without a TASKS collection.
    startup: Items | None = next(
        (
            collection
            for collection in collections
            if collection.items_directory.name == STARTUP_COLLECTION
        ),
        None,
    )
    if startup is None:
        return ""

    # Go through every item, the TASKS items first.
    lines: list[str] = []
    closed: list[tuple[str, str, str, Path, str]] = []
    collection: Items
    for collection in [startup] + [
        collection for collection in collections if collection is not startup
    ]:
        collection_type: CollectionType = collection.collection_type
        if not collection_type.in_startup:
            continue
        item: Item
        for item in collection.list_items():
            # Find the item's directory relative to TASKS.
            item_directory: Path = collection.directories[item.name]
            relative: str = Path(
                os.path.relpath(item_directory, startup.items_directory)
            ).as_posix()

            # Note a finished item for later.
            if item.state in collection_type.finished_states:
                closed.append(
                    (
                        closed_time(item, item_directory),
                        f"{collection.prefix}{item.tag}",
                        item.title,
                        item_directory,
                        relative,
                    )
                )
                continue

            # Import the `Details.md` and maybe the `Context.md` of
            # others.
            file_names: tuple[str, ...] = ("Details.md",)
            if item.state in collection_type.context_states:
                file_names += ("Context.md",)
            file_name: str
            for file_name in file_names:
                if (item_directory / file_name).is_file():
                    lines.append(f"@{relative}/{file_name}")

    # Get the number of summaries, which the test suite can change.
    limit: int = CLOSED_SUMMARIES
    with contextlib.suppress(ValueError):
        limit = int(os.environ.get(SUMMARIES_VARIABLE, limit))

    # Import the summaries of the most recently finished items.
    closed.sort(key=lambda entry: entry[0], reverse=True)
    for _, _, _, item_directory, relative in closed[:limit]:
        summary_file: str = (
            "Summary.md" if has_summary(item_directory) else "Details.md"
        )
        lines.append(f"@{relative}/{summary_file}")

    # The older ones go in `Closed.md`.
    older: list[tuple[str, str]] = [
        (tag, title) for _, tag, title, _, _ in closed[limit:]
    ]
    if older:
        lines.append("@Closed.md")

    # Write `Startup.md`, then `Closed.md`.
    startup_path: Path = startup.items_directory / "Startup.md"
    try:
        write_file(startup_path, "".join(f"{line}\n" for line in lines))
    except OSError as error:
        return f"Unable to write '{startup_path}': {error}"
    return write_closed(startup.items_directory / "Closed.md", older)


# Function `do_transfer()`:
def do_transfer(directory: Path, plan: dict[str, object], phase: int) -> str:
    """Do a transfer from a collection, starting at a phase.

    The plan names the target collection (a sibling of `directory`), the
    time, the "items" (each with the `TRANSFER_KEYS`) and the renames of
    the renumberings of the source and the target (as in
    `.renumber.json`).  Phase 1 moves the item directories to temporary
    names in the target, phase 2 renumbers the source, phase 3 renumbers
    the target to make room, and phase 4 fixes each item's headings and
    `.item.json` and gives it its new name.  Each step is skipped if it
    has already been done, and `.transfer.json` in `directory` records
    the plan and its phase until the end, when it is removed.

    Arguments:
    * `directory` (`Path`):
      The collection the items come from.
    * `plan` (`dict[str, object]`):
      The transfer plan, as in `.transfer.json`.
    * `phase` (`int`):
      The phase to start at.

    Returns:
    * (`str`): An empty string on success, or an error string on
      failure.
    """
    # Read the plan.
    marker: Path = directory / TRANSFER_FILE
    target: Path = directory.parent / str(plan["target"])
    copies: bool = TYPES.get(
        type_name(target), TYPES[DEFAULT_TYPE]
    ).has_sources
    stamp: str = str(plan["time"])
    items: list[dict[str, str]] = plan_list(plan, "items", TRANSFER_KEYS)

    # The test suite can interrupt the transfer after any step.
    limit: str = os.environ.get(INTERRUPT_VARIABLE, "")
    steps: list[int] = [0]

    def step() -> None:
        """Count a step, and interrupt if the test suite asks.

        Raises:
        * `RenumberInterrupted`: If the steps exceed the number in the
          `INTERRUPT_VARIABLE` environment variable.
        """
        steps[0] += 1
        if limit.isdecimal() and steps[0] > int(limit):
            raise RenumberInterrupted

    def save(next_phase: int) -> None:
        """Write the plan to `.transfer.json` with a phase.

        Arguments:
        * `next_phase` (`int`):
          The phase to record.

        Raises:
        * `OSError`: If `.transfer.json` can not be written.
        """
        write_file(
            marker, json.dumps({**plan, "phase": next_phase}, indent=2) + "\n"
        )

    # Phase 1: move the items to temporary names in the target.
    try:
        save(phase)
        if phase <= 1:
            item: dict[str, str]
            for item in items:
                if (directory / item["old"]).exists() and not (
                    target / item["temporary"]
                ).exists():
                    step()
                    (directory / item["old"]).rename(
                        target / item["temporary"]
                    )
            save(2)

        # Phases 2 and 3: renumber the source and then the target.
        number: int
        renumbered: Path
        key: str
        for number, (renumbered, key) in enumerate(
            ((directory, "source_renames"), (target, "target_renames")), 2
        ):
            if phase <= number:
                renames: list[dict[str, str]] = plan_list(
                    plan, key, RENAME_KEYS
                )
                if renames:
                    step()
                    error: str = do_renumber(renumbered, renames, 1)
                    if error:
                        return error
                save(number + 1)

        # Phase 4: fix each item and give it its new name.
        for item in items:
            temporary: Path = target / item["temporary"]
            if not temporary.exists():
                continue
            step()

            # Fix the number in the `Details.md` heading (a rule's is
            # the copy of its source, which is left alone).
            details_path: Path = temporary / "Details.md"
            details: str = "" if copies else read_file(details_path)
            prefix: str = f"# {item['old_number']} "
            if details.startswith(prefix):
                write_file(
                    details_path,
                    f"# {item['new_number']} {details[len(prefix) :]}",
                )

            # Fix the `Summary.md` heading.
            if item["summary"]:
                write_summary_heading(
                    temporary, summary_heading(item["new_tag"], item["title"])
                )

            # Record the transfer in `.item.json`.
            metadata: dict[str, object] = read_item(temporary)
            move: dict[str, str] = {
                "from": item["old_tag"],
                "to": item["new_tag"],
                "time": stamp,
            }
            moves: object = metadata.get("moves")
            moves = moves if isinstance(moves, list) else []
            if not moves or moves[-1] != move:
                moves.append(move)
            metadata.update(tag=item["tag"], updated=stamp, moves=moves)
            write_item(temporary, metadata)

            # Give the item its new name.
            temporary.rename(target / item["new"])

        # The transfer is done.
        marker.unlink()
    except (OSError, ValueError) as error:
        return (
            f"Unable to transfer items from '{directory}' to '{target}': "
            f"{error}"
        )

    # Report success.
    return ""


# Function `plan_list()`:
def plan_list(
    plan: dict[str, object], key: str, keys: tuple[str, ...]
) -> list[dict[str, str]]:
    """Return a list of JSON objects from a plan.

    Arguments:
    * `plan` (`dict[str, object]`):
      The plan.
    * `key` (`str`):
      The key of the list in `plan`.
    * `keys` (`tuple[str, ...]`):
      The keys that each entry must have.

    Returns:
    * (`list[dict[str, str]]`): The entries of the list.

    Raises:
    * `ValueError`: If it is not a list of JSON objects with the `keys`.
    """
    # The entries must be JSON objects with every key.
    entries: object = plan.get(key)
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) and all(name in entry for name in keys)
        for entry in entries
    ):
        raise ValueError(f"'{key}' is not a list of {', '.join(keys)}")
    return [{name: str(entry[name]) for name in keys} for entry in entries]


# Function `recover_transfers()`:
def recover_transfers(parent: Path) -> None:
    """Finish every interrupted transfer between collections.

    This is done before any collection is loaded, since a collection in
    the middle of a transfer can have gaps that must not be "fixed".
    The recovery, or a failure to recover, is reported to stderr.

    Arguments:
    * `parent` (`Path`):
      The directory that holds the collections.
    """
    # Look in each directory that holds the collections.
    try:
        directories: list[Path] = sorted(parent.iterdir())
    except OSError:
        return
    directory: Path
    for directory in directories:
        # Only a collection with a `.transfer.json` needs finishing.
        marker: Path = directory / TRANSFER_FILE
        if not (directory / COLLECTION_FILE).is_file() or not marker.exists():
            continue

        # Read the plan and finish it.
        error: str = ""
        plan: dict[str, object] = {}
        items: list[dict[str, str]] = []
        try:
            loaded: object = json.loads(read_file(marker))
            if not isinstance(loaded, dict):
                raise TypeError("it is not a JSON object")
            plan = loaded
            phase: int = int(str(plan["phase"]))
            items = plan_list(plan, "items", TRANSFER_KEYS)
        except (OSError, ValueError, TypeError, KeyError) as problem:
            error = f"Unable to read '{marker}': {problem!r}"
        else:
            error = do_transfer(directory, plan, phase)

        # Report the result.
        if error:
            print(
                f"Unable to finish an interrupted transfer: {error}",
                file=sys.stderr,
            )
        else:
            print(
                f"Finished an interrupted transfer from '{directory.name}' "
                f"to '{plan['target']}': "
                + ", ".join(
                    f"{item['old_tag']} -> {item['new_tag']}" for item in items
                ),
                file=sys.stderr,
            )


# Function `do_renumber()`:
def do_renumber(
    directory: Path, renames: list[dict[str, str]], phase: int
) -> str:
    """Do the renames of a renumbering in a collection, from a phase.

    Phase 1 renames the old directories to temporary names, phase 2
    renames those to the new names, and phase 3 rewrites the headings.
    Each step is skipped if it has already been done, and
    `.renumber.json` records the phase until the end, when it is
    removed.

    Arguments:
    * `directory` (`Path`):
      The collection.
    * `renames` (`list[dict[str, str]]`):
      The renames, each with the `RENAME_KEYS`.
    * `phase` (`int`):
      The phase to start at.

    Returns:
    * (`str`): An empty string on success, or an error string on
      failure.
    """
    # The test suite can interrupt the renumbering after any step.
    marker: Path = directory / RENUMBER_FILE
    limit: str = os.environ.get(INTERRUPT_VARIABLE, "")
    steps: list[int] = [0]

    def step() -> None:
        """Count a step, and interrupt if the test suite asks.

        Raises:
        * `RenumberInterrupted`: If the steps exceed the number in the
          `INTERRUPT_VARIABLE` environment variable.
        """
        steps[0] += 1
        if limit.isdecimal() and steps[0] > int(limit):
            raise RenumberInterrupted

    def path(rename: dict[str, str], key: str) -> Path:
        """Return the path of one of the names of a rename.

        Arguments:
        * `rename` (`dict[str, str]`):
          The rename.
        * `key` (`str`):
          "old", "temporary" or "new".

        Returns:
        * (`Path`): The path in the collection.
        """
        return directory / rename[key]

    # Record the plan and its phase.
    try:
        write_file(
            marker,
            json.dumps({"phase": phase, "renames": renames}, indent=2) + "\n",
        )

        # Phase 1: rename the old directories to temporary names.
        if phase == 1:
            rename: dict[str, str]
            for rename in renames:
                if (
                    path(rename, "old").exists()
                    and not path(rename, "temporary").exists()
                ):
                    step()
                    path(rename, "old").rename(path(rename, "temporary"))
            write_file(
                marker,
                json.dumps({"phase": 2, "renames": renames}, indent=2) + "\n",
            )

        # Phase 2: rename those to the new names.
        for rename in renames:
            if path(rename, "temporary").exists():
                step()
                path(rename, "temporary").rename(path(rename, "new"))

        # Phase 3: fix the number in each `Details.md` heading (a
        # rule's is the copy of its source, which is left alone).
        copies: bool = TYPES.get(
            type_name(directory), TYPES[DEFAULT_TYPE]
        ).has_sources
        for rename in renames:
            details_path: Path = path(rename, "new") / "Details.md"
            details: str = "" if copies else read_file(details_path)
            prefix: str = f"# {rename['old_number']} "
            if details.startswith(prefix):
                step()
                write_file(
                    details_path,
                    f"# {rename['new_number']} {details[len(prefix) :]}",
                )

        # The renumbering is done.
        marker.unlink()
    except OSError as error:
        return f"Unable to renumber items in '{directory}': {error}"

    # Report success.
    return ""


# Function `write_active_rules()`:
def write_active_rules(collections: list["Items"]) -> str:
    """Write `Active_Rules.md` into each collection with sources.

    Every line is an `@` import, relative to the collection, of the copy
    of an Active item's source, in number order, so that adding
    `@RULES/Active_Rules.md` to `CLAUDE.md` loads them.

    Arguments:
    * `collections` (`list[Items]`):
      Every collection.

    Returns:
    * (`str`): An empty string on success, or an error string on
      failure.
    """
    # Write `Active_Rules.md` in each rules collection.
    collection: Items
    for collection in collections:
        if not collection.collection_type.has_sources:
            continue

        # Import the copy of each Active rule's source.
        lines: list[str] = [
            f"@{collection.directories[item.name].name}/"
            f"{collection.copy_path(item).name}\n"
            for item in collection.list_items()
            if item.state == "Active"
            and item.source
            and collection.copy_path(item).is_file()
        ]

        # Write the imports.
        path: Path = collection.items_directory / ACTIVE_RULES
        try:
            write_file(path, "".join(lines))
        except OSError as error:
            return f"Unable to write '{path}': {error}"

    # Report success.
    return ""


# Function `write_rules_files()`:
def write_rules_files(collections: list["Items"]) -> str:
    """Write `RULES_FILE` into every collection.

    A file that already holds `RULES_TEXT` is left alone, so that its
    time does not change; any other contents (such as an edit by hand)
    are replaced.

    Arguments:
    * `collections` (`list[Items]`):
      Every collection.

    Returns:
    * (`str`): An empty string on success, or an error string on
      failure.
    """
    # Write the file in each collection that does not have it yet.
    collection: Items
    for collection in collections:
        path: Path = collection.items_directory / RULES_FILE
        with contextlib.suppress(OSError, ValueError):
            if read_file(path) == RULES_TEXT:
                continue
        try:
            write_file(path, RULES_TEXT)
        except OSError as error:
            return f"Unable to write '{path}': {error}"

    # Report success.
    return ""


# Function `check_claude_imports()`:
def check_claude_imports(root: Path) -> None:
    """Report each `@` import in `CLAUDE.md` whose file does not exist.

    `CLAUDE.md` should only import files that are known to exist, so
    that loading it never quietly leaves something out.  Only an import
    that looks like a file (its path has a `/` or a `.`) is checked, so
    that a word like `@dataclass` is not reported.  The messages go to
    stderr.

    Arguments:
    * `root` (`Path`):
      The directory that holds the collections and `CLAUDE.md`.
    """
    # Read `CLAUDE.md`, if there is one.
    claude: Path = root / "CLAUDE.md"
    try:
        text: str = read_file(claude)
    except (OSError, ValueError):
        return

    # Report each import of a file that does not exist.
    number: int
    path: str
    for number, path in markdown_imports(text):
        if ("/" in path or "." in path) and not (
            root / Path(path).expanduser()
        ).exists():
            print(
                f"CLAUDE.md imports @{path} (line {number}), which does "
                "not exist",
                file=sys.stderr,
            )


# Function `closed_time()`:
def closed_time(item: "Item", item_directory: Path) -> str:
    """Return when an item was last Closed, from its state history.

    Arguments:
    * `item` (`Item`):
      The item.
    * `item_directory` (`Path`):
      The item's directory.

    Returns:
    * (`str`): The UTC timestamp, or the item's updated time if the
      history does not say.
    """
    # Find the last change to a finished state in the history.
    with contextlib.suppress(OSError, ValueError):
        history: object = read_item(item_directory).get("history")
        change: object
        for change in reversed(history if isinstance(history, list) else []):
            if (
                isinstance(change, dict)
                and change.get("state") in FINISHED_STATES
            ):
                return str(change.get("time", item.updated))

    # Fall back to the updated time.
    return item.updated


# Function `write_closed()`:
def write_closed(closed_path: Path, older: list[tuple[str, str]]) -> str:
    """Write `Closed.md`, or remove it if there are no older items.

    Arguments:
    * `closed_path` (`Path`):
      The path of `Closed.md`.
    * `older` (`list[tuple[str, str]]`):
      The tag and title of each Closed item whose summary is not in
      `Startup.md`, newest first.

    Returns:
    * (`str`): An empty string on success, or an error string on
      failure.
    """
    # List the older items by tag and title.
    lines: list[str] = [
        "# Older Closed and Rejected Items",
        "",
        "<!-- Written by ai_contexts; do not edit. -->",
        "",
        "These items are only listed by tag and title; `ai_contexts TAG",
        "show` shows the rest.",
        "",
    ] + [f"- `{tag}` {title}" for tag, title in older]

    # Write the list, or remove it if it is empty.
    try:
        if older:
            write_file(closed_path, "\n".join(lines) + "\n")
        else:
            closed_path.unlink(missing_ok=True)
    except OSError as error:
        return f"Unable to write '{closed_path}': {error}"

    # Report success.
    return ""


# Function `print_items()`:
def print_items(
    items: list[Item],
    long: bool = False,
    priority: bool = False,
    prefix: str = "",
    old_numbers: list[str] | None = None,
) -> None:
    """Print one line per item: number, state, priority, tag and title.

    Arguments:
    * `items` (`list[Item]`):
      The items to print.
    * `long` (`bool`):
      True to also print the created and updated times, in the local
      time zone.
    * `priority` (`bool`):
      True to print the priority, with "-" for none.
    * `prefix` (`str`):
      The tag prefix.
    * `old_numbers` (`list[str] | None`):
      If given, the old number of each item, which starts its line with
      "->".
    """
    # Find the width of each column.
    old_width: int = max((len(old) for old in old_numbers or []), default=0)
    width: int = max((len(item.number) for item in items), default=0)
    tags: dict[tuple[int, ...], str] = {
        item.name: f"{prefix}{item.tag}" if item.tag else "" for item in items
    }
    tag_width: int = max((len(tag) for tag in tags.values()), default=0)
    state_width: int = max(len(state) for state in ALL_STATES)
    time_width: int = len("YYYY-MM-DD HH:MM")

    # Print a line for each item.
    index: int
    item: Item
    for index, item in enumerate(items):
        levels: str = (
            f"{'-' if item.priority is None else item.priority}  "
            if priority
            else ""
        )
        times: str = (
            f"{local_time(item.created):<{time_width}}  "
            f"{local_time(item.updated):<{time_width}}  "
            if long
            else ""
        )
        print(
            (f"{old_numbers[index]:<{old_width}} -> " if old_numbers else "")
            + f"{item.number:<{width}}  "
            f"{item.state:<{state_width}}  "
            f"{levels}{tags[item.name]:<{tag_width}}  {times}{item.title}"
        )


# Function `main()`:
def main() -> None:  # pragma: no cover
    """Run ai_contexts."""
    sys.exit(Items.run_command(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover
    main()
