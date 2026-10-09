#!/usr/bin/env python3
"""Manage the AI contexts that Claude Code loads, kept in Markdown files."""

import contextlib
import glob
import hashlib
import json
import os
import re
import shutil
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
       ai_contexts NAME create Create the collection directory NAME
       ai_contexts --test      Run the self tests in a temporary directory
       ai_contexts -h | --help Print this help message
       ai_contexts             List the collections, one line each

A COLLECTION is a directory containing a `.ai_contexts.json` file.  They
are found in the current directory, or else the nearest parent directory
that has any.  COLLECTION and COMMAND may be shortened to any unique
prefix, in any case (e.g. `ai_contexts t cl 2` closes item 2 in TASKS).
A new collection is created, after asking, next to the existing ones (or
else in the current directory) and is named exactly as typed.

Commands:
  create PLACE TITLE...   Create an item at PLACE (see below)
  create PLACE FILE...    In a rules collection, create a rule from each
                          FILE (or glob pattern), at PLACE and after
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
  pending [-r] NUMBER     Set the item state to Pending
  open [-r] NUMBER        Set the item state to Open
  reference [-r] NUMBER   Set the item state to Reference
  suspend [-r] NUMBER     Set the item state to Suspended
  close [-r] NUMBER       Set the item state to Closed
  reject [-r] NUMBER      Set the item state to Rejected
  activate [-r] NUMBER    Set the rule state to Active (rules collections)
  deactivate [-r] NUMBER  Set the rule state to InActive (rules collections)
  source NUMBER FILE      Make FILE the source of a rule, and copy it
  refresh NUMBER          Copy a rule's source over its copy, asking first
                          if the copy was edited in place
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
collections, and a read-only copy of it in the rule's directory.  Every
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
in any case) may be used wherever an item NUMBER is expected.

When priority is enabled for a collection, its items are listed by
priority first (0 to 3, then none) and the priority is shown."""

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
    * `has_sources` (`bool`): True if each item is a copy of a source
      file (see `Items.check_rules()`).

    Constructor:
    * `CollectionType(states, new_state, finished_states, context_states,
      state_commands, commands, files, in_startup, has_sources)`
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
        commands=("source", "refresh"),
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

# The file names that a source file can not have, since its copy goes into
# an item directory.
RESERVED_NAMES: frozenset[str] = frozenset(
    {"Details.md", "Context.md", "Summary.md"}
)

# An `@` import in Markdown: an `@` that starts a word, and the path after.
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

# The version of the format of the collections, kept in `.ai_contexts.json`.
FORMAT_VERSION: str = "0.1"

# The hidden JSON file that holds a renumbering while it is being done, so
# that an interrupted renumbering can be finished.
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

# The hidden JSON file that holds a transfer of items to another collection
# while it is being done, so that an interrupted transfer can be finished.
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

# The collection that holds `Startup.md` for all of the collections.
STARTUP_COLLECTION: str = "TASKS"

# The priority levels, from catastrophic (0) to low (3).
PRIORITIES: tuple[int, ...] = (0, 1, 2, 3)

# The seconds after a move or rename before the next one reminds the user
# to take a version control snapshot.  The test suite can change it with
# the environment variable named by `DELAY_VARIABLE`.
MOVE_RENAME_DELAY_SECONDS: float = 3600.0
DELAY_VARIABLE: str = "AI_CONTEXTS_TEST_MOVE_RENAME_DELAY_SECONDS"

# The places relative to an existing item.
PLACES: tuple[str, ...] = ("before", "after")

# A stand-in name for an item that is about to be created.
NEW_ITEM: tuple[int, ...] = (0,)

# The features that can be enabled for a collection in `.ai_contexts.json`.
FEATURES: tuple[str, ...] = ("priority",)

# The words that are left out of a tag.
TAG_IGNORED_WORDS: frozenset[str] = frozenset({"a", "an", "of", "the"})

# The commands of every type of collection, and the command that each one
# runs; each type adds its state commands (see `commands()`).
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
    """A renumbering interrupted by the test suite (`INTERRUPT_VARIABLE`).

    Attributes:
    * None beyond those of `Exception`.
    """


# Function `read_file()`:
def read_file(path: Path) -> str:
    """Return the contents of the UTF-8 text file at `path`."""
    return path.read_text(encoding="utf-8")


# Function `write_file()`:
def write_file(path: Path, text: str) -> None:
    """Write `text` to `path` as a UTF-8 text file."""
    path.write_text(text, encoding="utf-8")


# Function `new_metadata()`:
def new_metadata(state: str, stamp: str) -> dict[str, object]:
    """Return the metadata of a new item in `state` at time `stamp`.

    The "history" list records every state change with its time.
    """
    return {
        "state": state,
        "created": stamp,
        "updated": stamp,
        "history": [{"state": state, "time": stamp}],
    }


# Function `write_item()`:
def write_item(item_directory: Path, metadata: dict[str, object]) -> None:
    """Write the `metadata` into the `.item.json` of `item_directory`."""
    text: str = json.dumps(metadata, indent=2)
    write_file(item_directory / ITEM_FILE, f"{text}\n")


# Function `utc_stamp()`:
def utc_stamp(seconds: float) -> str:
    """Return `seconds` since the epoch as a UTC timestamp string.

    The timestamp is ISO 8601, like "2026-10-05T21:35:00Z".
    """
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Function `local_time()`:
def local_time(stamp: str) -> str:
    """Return the UTC timestamp `stamp` in the local time zone.

    Returns "-" if `stamp` is empty, or "?" if it is not a valid timestamp
    with a time zone.
    """
    if not stamp:
        return "-"
    try:
        moment: datetime = datetime.fromisoformat(stamp)
    except ValueError:
        return "?"
    if moment.tzinfo is None:
        return "?"
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


# Function `read_item()`:
def read_item(item_directory: Path) -> dict[str, object]:
    """Return the metadata in the `.item.json` of `item_directory`.

    An item directory in the old format, with a `.status` file instead, is
    migrated first, using the time of the `.status` file as the created
    and updated times.  Raises an `OSError` if a file can not be read or
    written, or a `ValueError` if `.item.json` is not a JSON object.
    """
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
    """Set the updated time in the `.item.json` of `item_directory` to now.

    If `state` is given, the state is changed too, and the change is
    appended to the "history" list.  The `fields` are also set, and a
    field set to None is removed.  Any other metadata is kept.  Returns
    the new updated time.  Raises an `OSError` or a `ValueError` like
    `read_item()`.
    """
    metadata: dict[str, object] = read_item(item_directory)
    stamp: str = utc_stamp(time.time())
    metadata["updated"] = stamp
    for key, value in (fields or {}).items():
        if value is None:
            metadata.pop(key, None)
        else:
            metadata[key] = value
    if state:
        history: object = metadata.get("history")
        if not isinstance(history, list):
            history = []
        history.append({"state": state, "time": stamp})
        metadata["state"] = state
        metadata["history"] = history
    write_item(item_directory, metadata)
    return stamp


# Function `matches()`:
def matches(word: str, names: Iterable[str]) -> list[str]:
    """Return the `names` that `word` abbreviates, ignoring case.

    A name equal to `word` (ignoring case) is the only match.  Otherwise
    every name that starts with `word` matches.
    """
    folded: str = word.casefold()
    exact: list[str] = [name for name in names if name.casefold() == folded]
    if exact:
        return exact
    return [name for name in names if name.casefold().startswith(folded)]


# Function `find_collections()`:
def find_collections(start: Path) -> list[Path]:
    """Return the collection directories nearest to `start`, sorted.

    `start` and then each of its parents is searched for sub-directories
    that contain a `.ai_contexts.json` file.  The ones in the first
    directory that has any are returned, or an empty list if none are
    found.  A collection in the old format, with a `.tracker.json` file
    instead, is migrated by renaming that file.
    """
    for directory in (start, *start.parents):
        try:
            found: list[Path] = sorted(
                path
                for path in directory.iterdir()
                if (path / COLLECTION_FILE).is_file()
                or (path / OLD_COLLECTION_FILE).is_file()
            )
        except OSError:
            continue
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
        if found:
            return found
    return []


# Function `type_name()`:
def type_name(directory: Path) -> str:
    """Return the type of the collection `directory`, from `.ai_contexts.json`.

    Returns `DEFAULT_TYPE` if the file can not be read or has no type; an
    unknown type is returned as it is (`Items` reports it).
    """
    try:
        settings: object = json.loads(read_file(directory / COLLECTION_FILE))
    except (OSError, ValueError):
        return DEFAULT_TYPE
    if isinstance(settings, dict):
        return str(settings.get("type", DEFAULT_TYPE))
    return DEFAULT_TYPE


# Function `commands()`:
def commands(name: str = "") -> dict[str, str]:
    """Return the commands of collection type `name`, or of every type.

    Each command is mapped to the command that it runs.
    """
    type_commands: Iterable[str] = (
        [*TYPES[name].state_commands, *TYPES[name].commands]
        if name in TYPES
        else [*STATE_COMMANDS, *TYPE_COMMANDS]
    )
    return {**COMMANDS, **{command: command for command in type_commands}}


# Function `sha256_of()`:
def sha256_of(path: Path) -> str:
    """Return the SHA-256 of the file at `path`, in hexadecimal.

    Raises an `OSError` if the file can not be read.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Function `markdown_imports()`:
def markdown_imports(text: str) -> list[tuple[int, str]]:
    """Return the line number and path of each `@` import in `text`.

    Imports in fenced code blocks and in code spans are left out, since
    Claude Code does not follow them.
    """
    found: list[tuple[int, str]] = []
    fence: str = ""
    for number, line in enumerate(text.splitlines(), 1):
        stripped: str = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            continue
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            continue
        found += [
            (number, path)
            for path in IMPORT_PATTERN.findall(re.sub(r"`[^`]*`", "", line))
        ]
    return found


# Function `expand_files()`:
def expand_files(arguments: list[str]) -> list[Path] | str:
    """Return the files named by `arguments`, expanding glob patterns.

    An argument with any of `GLOB_CHARACTERS` is a pattern, which must
    match at least one file; its matches are sorted.  Returns an error
    string if an argument is not a file or a pattern matches nothing.
    """
    files: list[Path] = []
    for argument in arguments:
        if any(character in argument for character in GLOB_CHARACTERS):
            matched: list[str] = sorted(glob.glob(argument))
            if not matched:
                return f"No files match '{argument}'"
            files += [Path(path) for path in matched]
        else:
            files.append(Path(argument))
    for path in files:
        if not path.is_file():
            return f"'{path}' is not a file"
    return files


# Function `base_tag()`:
def base_tag(title: str) -> str:
    """Return the tag for `title`, before it is made unique.

    The tag is the first letter or digit of each word in lower case.
    Punctuation is dropped, a hyphenated word only gives its first letter,
    and the words in `TAG_IGNORED_WORDS` are left out.  If every word is
    left out, the first letter or digit of `title` is used.
    """
    tag: str = ""
    for word in title.split():
        characters: str = "".join(
            character for character in word if character.isalnum()
        ).casefold()
        if characters and characters not in TAG_IGNORED_WORDS:
            tag += characters[0]
    if not tag:
        tag = next(
            (character for character in title if character.isalnum()), ""
        ).casefold()
    return tag


# Function `unique_tag()`:
def unique_tag(base: str, used: Iterable[str]) -> str:
    """Return `base`, or `base` plus the lowest number from 2 not `used`."""
    used_tags: set[str] = set(used)
    if base not in used_tags:
        return base
    number: int = 2
    while f"{base}{number}" in used_tags:
        number += 1
    return f"{base}{number}"


# Function `parse_priority()`:
def parse_priority(level: str) -> int | None | str:
    """Convert a priority `level` like "2" into 2, or "-" into None.

    Returns an error string if `level` is not a valid priority.
    """
    if level == "-":
        return None
    if level.isdecimal() and int(level) in PRIORITIES:
        return int(level)
    return (
        f"Invalid priority '{level}': it must be one of "
        f"{', '.join(str(priority) for priority in PRIORITIES)} or -"
    )


# Function `number_text()`:
def number_text(name: tuple[int, ...]) -> str:
    """Return `name` as period separated numbers, like "1.2.3"."""
    return ".".join(str(part) for part in name)


# Function `tag_prefix()`:
def tag_prefix(collection_name: str) -> str:
    """Return the tag prefix of a collection, like "T." for "TASKS"."""
    return f"{collection_name[:1].upper()}."


# Function `tag_collection()`:
def tag_collection(word: str, names: list[str]) -> str:
    """Return the collection of `names` whose tag prefix starts `word`.

    Returns an empty string unless `word` looks like a tag (e.g. "I.dbzib")
    and its prefix belongs to one of the `names`.
    """
    if len(word) < 3 or word[1] != ".":
        return ""
    return next(
        (name for name in names if tag_prefix(name) == word[:2].upper()), ""
    )


# Function `summary_heading()`:
def summary_heading(tag: str, title: str) -> str:
    """Return the first line of an item's `Summary.md`."""
    return f"# Summary of `{tag}` {title}"


# Function `write_summary_heading()`:
def write_summary_heading(item_directory: Path, heading: str) -> None:
    """Make `heading` the first line of the item's `Summary.md`.

    The old heading is replaced, or the file is made if it is missing.
    Raises an `OSError` if the file can not be read or written.
    """
    path: Path = item_directory / "Summary.md"
    text: str = read_file(path) if path.exists() else ""
    first, _, rest = text.partition("\n")
    if not first.startswith("# Summary of "):
        rest = text
    write_file(path, f"{heading}\n{rest}")


# Function `has_summary()`:
def has_summary(item_directory: Path) -> bool:
    """Return whether the item's `Summary.md` says more than its heading."""
    try:
        text: str = read_file(item_directory / "Summary.md")
    except OSError:
        return False
    if text.startswith("# Summary of "):
        text = text.partition("\n")[2]
    return bool(text.strip())


# Function `tag_references()`:
def tag_references(root: Path, tag: str) -> list[Path]:
    """Return the writable `.md` files under `root` that mention `tag`.

    Hidden directories (like `.git`) and symbolic links are skipped.  A
    mention is the whole tag, so "T.fbm" is not found in "T.fbm2" or
    "XT.fbm".
    """
    pattern: re.Pattern[str] = tag_pattern(tag)
    found: list[Path] = []
    for directory, subdirectories, file_names in os.walk(root):
        subdirectories[:] = sorted(
            name for name in subdirectories if not name.startswith(".")
        )
        for file_name in sorted(file_names):
            path: Path = Path(directory) / file_name
            if (
                file_name.endswith(".md")
                and not path.is_symlink()
                and os.access(path, os.W_OK)
            ):
                with contextlib.suppress(OSError, UnicodeDecodeError):
                    if pattern.search(read_file(path)):
                        found.append(path)
    return found


# Function `tag_pattern()`:
def tag_pattern(tag: str) -> re.Pattern[str]:
    """Return a pattern that finds the whole `tag` in text."""
    return re.compile(rf"(?<![\w.]){re.escape(tag)}(?!\w)")


# Function `parse_number()`:
def parse_number(number: str) -> tuple[int, ...] | str:
    """Convert a number like "1.2.3" into a name like (1, 2, 3).

    Returns the name, or an error string if the number is invalid.
    """
    if not number:
        return "Item number is empty"
    name_list: list[int] = []
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
    """Return `title` cleaned up for use in an item directory name.

    Hyphens and underscores separate words, periods are kept, other
    punctuation is removed, a word with no letters or digits is dropped,
    the first word is capitalized and the words are joined by
    underscores.  The result can be pasted into a shell command without
    quoting.  Returns an empty string if `title` has no words.
    """
    remove: str = (
        string.punctuation.replace("-", "").replace("_", "").replace(".", "")
    )
    words: list[str] = [
        word
        for word in title.translate(str.maketrans("-_", "  ", remove)).split()
        if any(character.isalnum() for character in word)
    ]
    if not words:
        return ""
    words[0] = words[0][0].upper() + words[0][1:]
    return "_".join(words)


# Function `parse_recursive()`:
def parse_recursive(
    command: str,
    arguments: list[str],
    resolve: Callable[[str], tuple[int, ...] | str] = parse_number,
) -> tuple[tuple[int, ...], bool] | str:
    """Parse the `[-r] NUMBER` arguments of `command`.

    Returns the item name and whether `-r` was given, or an error string.
    """
    recursive: bool = False
    numbers: list[str] = []
    for argument in arguments:
        if argument in ("-r", "--recursive"):
            recursive = True
        else:
            numbers.append(argument)
    if len(numbers) != 1:
        return f"Usage: ai_contexts COLLECTION {command} [-r] NUMBER"
    name: tuple[int, ...] | str = resolve(numbers[0])
    if isinstance(name, str):
        return name
    return name, recursive


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
    * `Item(name, title, state, created, updated, tag, priority, source)`
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

        The name must be a non-empty tuple of positive integers and the
        state must be one of `ALL_STATES` (`Items` checks that it is one of
        its type's states).  Raises a `ValueError` if not.
        """
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
        if self.state not in ALL_STATES:
            raise ValueError(
                f"Item state {self.state!r} is not one of "
                f"{', '.join(ALL_STATES)}"
            )

    # Method `Item.number()`:
    @property
    def number(self) -> str:
        """Return the name as period separated numbers, like "1.2.3"."""
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
        """Initialize the collection of items in `items_directory`.

        Creates `items_directory` and its `.ai_contexts.json` file if they are
        not already present.  If the directory can not be created or is
        not writable, an error is printed to stderr and `self.error` is
        set to a non-empty error string.
        """
        self.items_directory: Path = items_directory
        self.items: dict[tuple[int, ...], Item] = {}
        self.directories: dict[tuple[int, ...], Path] = {}
        self.error: str = ""
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
        if error:
            print(error, file=sys.stderr)

    # Method `Items.prefix()`:
    @property
    def prefix(self) -> str:
        """Return the tag prefix of this collection, like "T."."""
        return tag_prefix(self.items_directory.name)

    # Method `Items.collection_type_name()`:
    @property
    def collection_type_name(self) -> str:
        """Return the name of this collection's type, like "items"."""
        return str(self.settings.get("type", DEFAULT_TYPE))

    # Method `Items.collection_type()`:
    @property
    def collection_type(self) -> CollectionType:
        """Return this collection's type."""
        return TYPES[self.collection_type_name]

    # Method `Items.resolve()`:
    def resolve(self, word: str) -> tuple[int, ...] | str:
        """Return the name of the item that `word` gives.

        `word` is an item number like "1.2.3", or a tag with or without
        the collection prefix, in any case (e.g. "T.fbm" or "fbm").
        Returns an error string if `word` is neither.
        """
        if word and all(
            character.isdecimal() or character == "." for character in word
        ):
            return parse_number(word)
        folded: str = word.casefold()
        for item in self.items.values():
            if item.tag and folded in (
                item.tag.casefold(),
                f"{self.prefix}{item.tag}".casefold(),
            ):
                return item.name
        return f"Invalid item number or tag '{word}'"

    # Method `Items.show()`:
    def show(
        self,
        items: list[Item],
        long: bool = False,
        old_numbers: list[str] | None = None,
    ) -> None:
        """Print `items` with this collection's tag prefix and priority.

        If `old_numbers` is given, each item's old number comes first.
        """
        print_items(
            items, long, self.priority_enabled, self.prefix, old_numbers
        )

    # Method `Items.priority_enabled()`:
    @property
    def priority_enabled(self) -> bool:
        """Return whether priority is enabled for this collection."""
        return self.settings.get("priority") is True

    # Method `Items.has_file()`:
    def has_file(self, file_name: str) -> bool:
        """Return whether the items of this collection have `file_name`."""
        return file_name in self.collection_type.files

    # Method `Items.root()`:
    @property
    def root(self) -> Path:
        """Return the real path of the directory that holds the collections.

        The sources of rules are kept relative to it.
        """
        return self.items_directory.parent.resolve()

    # Method `Items.copy_path()`:
    def copy_path(self, item: Item) -> Path:
        """Return where the copy of `item`'s source goes.

        It is in the item directory, with the source file's name.
        """
        return self.directories[item.name] / Path(item.source).name

    # Method `Items.save_settings()`:
    def save_settings(self, settings: dict[str, object]) -> str:
        """Write `settings` to `.ai_contexts.json` and keep them.

        Returns an empty string on success, or an error string on failure.
        """
        collection_path: Path = self.items_directory / COLLECTION_FILE
        try:
            write_file(collection_path, json.dumps(settings, indent=2) + "\n")
        except OSError as error:
            return f"Unable to write '{collection_path}': {error}"
        self.settings = settings
        return ""

    # Method `Items.set_feature()`:
    def set_feature(self, feature: str, enabled: bool) -> str:
        """Enable or disable `feature` in `.ai_contexts.json`.

        Returns an empty string on success, or an error string on failure.
        """
        return self.save_settings({**self.settings, feature: enabled})

    # Method `Items.confirm_snapshot()`:
    def confirm_snapshot(self, ask: Callable[[str], str]) -> bool:
        """Before a move, rename or transfer, recommend a snapshot.

        If there has been no move, rename or transfer in this collection for
        `MOVE_RENAME_DELAY_SECONDS` (or the seconds in the `DELAY_VARIABLE`
        environment variable), a reminder is printed to stderr and `ask`
        asks whether to continue.  Returns whether to go ahead.
        """
        delay: float = MOVE_RENAME_DELAY_SECONDS
        with contextlib.suppress(ValueError):
            delay = float(os.environ.get(DELAY_VARIABLE, delay))
        last: object = self.settings.get("last_move_or_rename")
        try:
            elapsed: float = (
                time.time() - datetime.fromisoformat(str(last)).timestamp()
            )
        except ValueError:
            elapsed = delay
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
        return True

    # Method `Items.note_move_or_rename()`:
    def note_move_or_rename(self) -> str:
        """Save the time of a move or rename in `.ai_contexts.json`.

        Returns an empty string on success, or an error string on failure.
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
        for item_directory in sorted(self.items_directory.iterdir()):
            if not item_directory.is_dir():
                continue
            number, _, cleaned_title = item_directory.name.partition("_")
            name: tuple[int, ...] | str = parse_number(number)
            if isinstance(name, str):
                print(f"Skipping '{item_directory}': {name}", file=sys.stderr)
                continue
            title: str = cleaned_title.replace("_", " ")
            try:
                metadata: dict[str, object] = read_item(item_directory)
                state: str = str(metadata.get("state"))
                details: str = read_file(item_directory / "Details.md")
                heading: str = details.partition("\n")[0]
            except (OSError, ValueError) as error:
                print(f"Skipping '{item_directory}': {error}", file=sys.stderr)
                continue
            prefix: str = f"# {number} "
            if heading.startswith(prefix):
                title = heading[len(prefix) :].strip()
            states: tuple[str, ...] = self.collection_type.states
            if state not in states:
                print(
                    f"Skipping '{item_directory}': its state {state!r} is "
                    f"not one of {', '.join(states)}",
                    file=sys.stderr,
                )
                continue
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
        self.add_missing_tags()
        self.add_missing_summaries()
        self.fix_gaps()
        self.check_items()
        if self.collection_type.has_sources:
            self.check_rules()

    # Method `Items.missing_names()`:
    def missing_names(self) -> list[tuple[int, ...]]:
        """Return the sorted names that are missing from the numbering.

        These are the absent parents of items and the absent earlier
        siblings of items and of their parents.
        """
        missing: set[tuple[int, ...]] = set()
        for name in self.items:
            for length in range(1, len(name) + 1):
                prefix: tuple[int, ...] = name[:length]
                missing.update(
                    prefix[:-1] + (part,)
                    for part in range(1, prefix[-1] + 1)
                    if prefix[:-1] + (part,) not in self.items
                )
        return sorted(missing)

    # Method `Items.gap_free_names()`:
    def gap_free_names(
        self, names: Iterable[tuple[int, ...]] | None = None
    ) -> dict[tuple[int, ...], tuple[int, ...]]:
        """Return the new name of each item whose name must change.

        The items are `names`, or else all of them.  Items keep their
        order.  An item whose parent is missing becomes a child of its
        nearest existing ancestor.
        """
        present: set[tuple[int, ...]] = set(
            self.items if names is None else names
        )
        new_names: dict[tuple[int, ...], tuple[int, ...]] = {}
        counts: dict[tuple[int, ...], int] = {}
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
        return {old: new for old, new in new_names.items() if old != new}

    # Method `Items.renumber()`:
    def renumber(
        self, new_names: dict[tuple[int, ...], tuple[int, ...]]
    ) -> str:
        """Give the items in `new_names` their new names.

        Each item directory is renamed (via a temporary name, so that the
        new names can not collide with the old ones) and the heading of
        its `Details.md` is rewritten.  The plan is first written to
        `.renumber.json`, which is removed at the end, so that an
        interrupted renumbering is finished the next time the collection
        is loaded.  Returns an empty string on success, or an error string
        on failure.
        """
        if not new_names:
            return ""
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
        """Return the renames that give the items `new_names`.

        Each has the `RENAME_KEYS` of `.renumber.json`, in name order.
        """
        renames: list[dict[str, str]] = []
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
        return renames

    # Method `Items.apply_renames()`:
    def apply_renames(
        self, new_names: dict[tuple[int, ...], tuple[int, ...]]
    ) -> None:
        """Give the items `new_names` in memory, after their directories."""
        moving: list[Item] = [self.items[old] for old in sorted(new_names)]
        directories: list[Path] = [
            self.directories[item.name] for item in moving
        ]
        for item in moving:
            del self.items[item.name]
            del self.directories[item.name]
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
        marker: Path = self.items_directory / RENUMBER_FILE
        if not marker.exists():
            return
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

        What ai_contexts maintains is fixed: the number in the `# N Title`
        heading of `Details.md` and the heading of `Summary.md`.  What a
        human maintains is reported, with what to do about it: a
        `Details.md` without that heading, a title that no longer matches
        the directory name, and items that share a tag.  Everything goes
        to stderr.
        """
        messages: list[str] = []
        tags: dict[str, list[str]] = {}
        for item in self.list_items():
            item_directory: Path = self.directories[item.name]
            where: str = f"'{item_directory}'"
            tags.setdefault(item.tag, []).append(item.number)
            try:
                details_path: Path = item_directory / "Details.md"
                details: str = read_file(details_path)
                heading, _, rest = details.partition("\n")
                words: list[str] = heading.split(" ", 2)
                if (
                    len(words) == 3
                    and words[0] == "#"
                    and words[1] != item.number
                    and not isinstance(parse_number(words[1]), str)
                ):
                    write_file(
                        details_path, f"# {item.number} {words[2]}\n{rest}"
                    )
                    item.title = words[2].strip()
                    messages.append(
                        f"Fixed the item number in the heading of {where}"
                    )
                elif not heading.startswith(f"# {item.number} "):
                    messages.append(
                        f"{where}: its Details.md does not start with a "
                        f"'# {item.number} TITLE' heading; `ai_contexts "
                        f"{self.prefix}{item.tag} rename to TITLE` adds one"
                    )
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
        for tag, numbers in sorted(tags.items()):
            if len(numbers) > 1:
                messages.append(
                    f"Items {', '.join(numbers)} in '{self.items_directory}' "
                    f"share the tag {self.prefix}{tag}; rename one of them"
                )
        for message in messages:
            print(message, file=sys.stderr)

    # Method `Items.check_rules()`:
    def check_rules(self) -> None:
        """Refresh and check the copies of the rules' sources.

        Each rule with a source has its copy refreshed (see
        `refresh_rule()`).  A rule without a source, an Active rule without
        a copy, a copy with an `@` import of a file (relative to the
        source; a rule must stand alone) and a copy that is the same as a
        file that `CLAUDE.md` imports directly are reported.  Everything
        goes to stderr.
        """
        messages: list[str] = []
        imported: dict[str, str] = self.claude_imports()
        for item in self.list_items():
            tag: str = f"{self.prefix}{item.tag}"
            if not item.source:
                messages.append(
                    f"{tag} has no source; `ai_contexts {tag} source PATH` "
                    "sets one"
                )
                continue
            message: str = self.refresh_rule(item)
            if message:
                messages.append(message)
            copy_path: Path = self.copy_path(item)
            if not copy_path.is_file():
                if item.state == "Active":
                    messages.append(
                        f"{tag} is Active but has no copy of its source "
                        f"'{item.source}'"
                    )
                continue
            try:
                text: str = read_file(copy_path)
                copy_hash: str = sha256_of(copy_path)
            except (OSError, ValueError) as error:
                messages.append(f"Unable to check {tag}: {error}")
                continue
            source_directory: Path = (self.root / item.source).parent
            for number, path in markdown_imports(text):
                if (source_directory / Path(path).expanduser()).is_file():
                    messages.append(
                        f"{tag}: its copy imports @{path} (line {number}); "
                        "a rule must stand alone"
                    )
            same: str = imported.get(copy_hash, "")
            if same:
                messages.append(
                    f"{tag} is the same as '{same}', which CLAUDE.md also "
                    "imports"
                )
        for message in messages:
            print(message, file=sys.stderr)

    # Method `Items.claude_imports()`:
    def claude_imports(self) -> dict[str, str]:
        """Return the files that `CLAUDE.md` imports, keyed by SHA-256.

        `CLAUDE.md` is in the directory that holds the collections.  An
        import that is not a readable file is left out.
        """
        claude: Path = self.items_directory.parent / "CLAUDE.md"
        try:
            text: str = read_file(claude)
        except (OSError, ValueError):
            return {}
        imported: dict[str, str] = {}
        for _, path in markdown_imports(text):
            with contextlib.suppress(OSError):
                imported[
                    sha256_of(claude.parent / Path(path).expanduser())
                ] = path
        return imported

    # Method `Items.refresh_rule()`:
    def refresh_rule(self, item: Item, force: bool = False) -> str:
        """Refresh the copy of the source of rule `item`.

        The copy is left alone if it is the same as the source (the hash
        is recorded if it was not), or if it was edited in place (its hash
        is not the recorded one), unless `force`, or if the source is
        missing.  Otherwise the source is copied to a temporary file,
        which is made read-only and then replaces the copy, and its hash
        and the time are recorded in `.item.json`.  Returns what was done
        or what is wrong, or an empty string if nothing was done.
        """
        tag: str = f"{self.prefix}{item.tag}"
        item_directory: Path = self.directories[item.name]
        source_path: Path = self.root / item.source
        copy_path: Path = self.copy_path(item)
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
            if copy_hash and copy_hash == source_hash:
                if recorded != copy_hash:
                    metadata["sha256"] = copy_hash
                    metadata.setdefault("refreshed", utc_stamp(time.time()))
                    write_item(item_directory, metadata)
                return ""
            if copy_hash and copy_hash != recorded and not force:
                return (
                    f"{tag}: its copy '{copy_path}' was edited in place; "
                    f"`ai_contexts {tag} refresh` replaces it with its source "
                    f"'{item.source}'"
                )
            if not source_hash:
                return f"{tag}: its source '{item.source}' is missing" + (
                    "; its last copy is kept" if copy_hash else ""
                )
            temporary: Path = item_directory / COPY_TEMPORARY
            temporary.unlink(missing_ok=True)
            temporary.write_bytes(source)
            temporary.chmod(0o444)
            temporary.replace(copy_path)
            metadata["sha256"] = source_hash
            metadata["refreshed"] = utc_stamp(time.time())
            write_item(item_directory, metadata)
        except (OSError, ValueError) as error:
            return f"Unable to refresh {tag}: {error}"
        return f"Refreshed {tag} from '{item.source}'"

    # Method `Items.fix_gaps()`:
    def fix_gaps(self) -> None:
        """Renumber the items if there are gaps, reporting it to stderr.

        Gaps only appear when item directories are removed by hand.
        """
        new_names: dict[tuple[int, ...], tuple[int, ...]] = (
            self.gap_free_names()
        )
        if not new_names:
            return
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
        error: str = self.renumber(new_names)
        if error:
            print(error, file=sys.stderr)

    # Method `Items.add_missing_summaries()`:
    def add_missing_summaries(self) -> None:
        """Give an empty `Summary.md` to every item that does not have one.

        This is for items made before `Summary.md` existed, so it is only
        done if the collection's type has a `Summary.md`.  A file that can
        not be written is reported to stderr.
        """
        if not self.has_file("Summary.md"):
            return
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

        This is for items made before tags existed, so the updated time is
        not changed.  A tag that can not be written is reported to stderr.
        """
        for item in self.list_items():
            if item.tag:
                continue
            tag: str = unique_tag(
                base_tag(item.title),
                (other.tag for other in self.items.values()),
            )
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
            item.tag = tag

    # Method `Items.list_items()`:
    def list_items(self, name: tuple[int, ...] = ()) -> list[Item]:
        """Return the items starting with `name`, sorted by name.

        An empty `name` returns all of the items.
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
        """Create a new Item at `number`, or `place` ("before" or "after")
        the existing item `number` (a number or tag).

        The later items are renumbered to make room.  Returns the new
        Item, or an error string if it can not be created.
        """
        if place:
            return self.create_at_place(number, title, place)
        name: tuple[int, ...] | str = parse_number(number)
        if isinstance(name, str):
            return name
        number = ".".join(str(part) for part in name)
        sub_directories: set[str] = {
            path.name.split("_", 1)[0]
            for path in self.items_directory.iterdir()
            if path.is_dir()
        }
        if name in self.items or number in sub_directories:
            return f"Item '{number}' already exists"
        if len(name) > 1 and name[:-1] not in self.items:
            return (
                f"Item '{number}' can not be created: "
                f"{number_text(name[:-1])} does not exist"
            )
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
        return self.make_item(name, title)

    # Method `Items.create_at_place()`:
    def create_at_place(self, word: str, title: str, place: str) -> Item | str:
        """Create a new Item `place` ("before" or "after") item `word`.

        Returns the new Item, or an error string if it can not be created.
        """
        target: tuple[int, ...] | str = self.resolve(word)
        if isinstance(target, str):
            return target
        planned: (
            tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]
            | str
        ) = self.plan_place([], place, target)
        if isinstance(planned, str):
            return planned
        new_names, name = planned
        if not clean_title(title):
            return f"Item '{number_text(name)}' has an empty title"
        error: str = self.renumber(new_names)
        if error:
            return error
        return self.make_item(name, title)

    # Method `Items.make_item()`:
    def make_item(self, name: tuple[int, ...], title: str) -> Item | str:
        """Make the directory and files of a new item `name`.

        Returns the new Item, or an error string if it can not be made.
        """
        number: str = number_text(name)
        title = title.strip()
        cleaned_title: str = clean_title(title)
        if not cleaned_title:
            return f"Item '{number}' has an empty title"
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
        try:
            item_directory.mkdir()
            write_item(
                item_directory, {**new_metadata(item.state, stamp), "tag": tag}
            )
            if self.has_file("Context.md"):
                write_file(
                    item_directory / "Context.md", "# LLM Agent Context Log\n"
                )
            write_file(item_directory / "Details.md", f"# {number} {title}\n")
            if self.has_file("Summary.md"):
                write_summary_heading(
                    item_directory,
                    summary_heading(f"{self.prefix}{tag}", title),
                )
        except OSError as error:
            return (
                f"Unable to create item directory '{item_directory}': {error}"
            )
        self.items[name] = item
        self.directories[name] = item_directory
        return item

    # Method `Items.select_items()`:
    def select_items(
        self, name: tuple[int, ...], recursive: bool = False
    ) -> list[Item] | str:
        """Return item `name`, and its children if `recursive`.

        Returns an error string if no item matches.
        """
        number: str = ".".join(str(part) for part in name)
        if recursive:
            selected: list[Item] = self.list_items(name)
            if not selected:
                return f"No items match '{number}'"
            return selected
        if name in self.items:
            return [self.items[name]]
        return f"Item '{number}' does not exist"

    # Method `Items.rename_item()`:
    def rename_item(self, name: tuple[int, ...], title: str) -> Item | str:
        """Change the title of item `name`.

        The item directory is renamed to match, and the heading line of its
        `Details.md` is rewritten, or added if it is missing, as is the
        heading of its `Summary.md`.  The tag is
        made from the new title, unless it would be the same as before.
        The updated time is set to now.  Returns the renamed item, or an
        error string if it can not be renamed.
        """
        number: str = ".".join(str(part) for part in name)
        if name not in self.items:
            return f"Item '{number}' does not exist"
        title = title.strip()
        cleaned_title: str = clean_title(title)
        if not cleaned_title:
            return f"Item '{number}' has an empty title"
        old_directory: Path = self.directories[name]
        new_directory: Path = (
            self.items_directory / f"{number}_{cleaned_title}"
        )
        if new_directory != old_directory and new_directory.exists():
            return f"'{new_directory}' already exists"
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
        details_path: Path = old_directory / "Details.md"
        try:
            details: str = read_file(details_path)
            heading, _, rest = details.partition("\n")
            if not heading.startswith(f"# {number} "):
                rest = details
            write_file(details_path, f"# {number} {title}\n{rest}")
            if self.has_file("Summary.md"):
                write_summary_heading(
                    old_directory,
                    summary_heading(f"{self.prefix}{tag}", title),
                )
            updated: str = update_item(old_directory, fields={"tag": tag})
            old_directory.rename(new_directory)
        except (OSError, ValueError) as error:
            return f"Unable to rename item '{number}': {error}"
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
        """Plan putting the `moving` siblings (or new items) at a place.

        `place` is "" for the free number `target`, or "before" or "after"
        the existing item `target`.  `moving` is empty for a new item.  The
        names refer to the items before anything moves.  Returns the new
        name of every item whose name changes, and the new name of the
        first moved (or new) item, or an error string if the place is not
        valid.  When `moving` is empty, room is made for `count` new
        sibling items, numbered from the first one.
        """
        for name in moving:
            if name not in self.items:
                return f"Item '{number_text(name)}' does not exist"
        children: dict[tuple[int, ...], list[tuple[int, ...]]] = {(): []}
        for name in sorted(self.items):
            children.setdefault(name, [])
            children[name[:-1]].append(name)
        moved: set[tuple[int, ...]] = {
            item.name for name in moving for item in self.list_items(name)
        }
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
        if moving:
            # In place, since `siblings` may be the same list.
            children[moving[0][:-1]][:] = [
                name for name in children[moving[0][:-1]] if name not in moving
            ]
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
        for new_item in new_items:
            children[new_item] = []
        new_names: dict[tuple[int, ...], tuple[int, ...]] = {}

        def number(
            parent: tuple[int, ...], new_parent: tuple[int, ...]
        ) -> None:
            for position, name in enumerate(children[parent], 1):
                new_names[name] = new_parent + (position,)
                number(name, new_names[name])

        number((), ())
        first: tuple[int, ...] = new_names[(moving or new_items)[0]]
        return {
            old: new
            for old, new in new_names.items()
            if old != new and old not in new_items
        }, first

    # Method `Items.resolve_range()`:
    def resolve_range(self, word: str) -> list[tuple[int, ...]] | str:
        """Return the names that `word` gives.

        `word` is a number or tag (see `resolve()`), or a range of
        siblings like "1.2.5-6".  Every item in a range must exist.
        Returns an error string if `word` is not valid.
        """
        if "-" not in word:
            name: tuple[int, ...] | str = self.resolve(word)
            return name if isinstance(name, str) else [name]
        first_text, _, last_text = word.rpartition("-")
        first: tuple[int, ...] | str = parse_number(first_text)
        if isinstance(first, str):
            return first
        if not last_text.isdecimal() or int(last_text) <= first[-1]:
            return (
                f"Invalid range '{word}': it must be like 1.2.5-6, with the "
                "last number greater than the one before the '-'"
            )
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
        """Delete the items `names`, and their children if `recursive`.

        An item with children is only deleted if `recursive`, and then only
        if `ask` gets a yes answer.  Each item directory is removed along
        with everything in it, and the later items are renumbered so that
        there are no gaps.  Returns the deleted items and the renumbered
        items keyed by their old numbers, or an error string on failure.
        """
        for name in names:
            if name not in self.items:
                return f"Item '{number_text(name)}' does not exist"
        doomed: list[Item] = [
            item for name in names for item in self.list_items(name)
        ]
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
        for item in doomed:
            item_directory: Path = self.directories[item.name]
            try:
                shutil.rmtree(item_directory)
            except OSError as error:
                return f"Unable to delete '{item_directory}': {error}"
            del self.items[item.name]
            del self.directories[item.name]
        new_names: dict[tuple[int, ...], tuple[int, ...]] = (
            self.gap_free_names()
        )
        renumbered: dict[str, Item] = {
            number_text(old): self.items[old] for old in sorted(new_names)
        }
        failure: str = self.renumber(new_names)
        if failure:
            return failure
        return doomed, renumbered

    # Method `Items.move_items()`:
    def move_items(
        self, names: list[tuple[int, ...]], place: str, target: tuple[int, ...]
    ) -> dict[str, Item] | str:
        """Move the sibling items `names`, with their children, to a place.

        `place` and `target` are as for `plan_place()`.  Returns the
        renumbered items keyed by their old numbers, or an error string on
        failure.
        """
        planned: (
            tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]
            | str
        ) = self.plan_place(names, place, target)
        if isinstance(planned, str):
            return planned
        new_names: dict[tuple[int, ...], tuple[int, ...]] = planned[0]
        error: str = self.renumber(new_names)
        if error:
            return error
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
        """Check a transfer of the items `names` (see `transfer_items()`).

        Returns the name in `target` of the place `word`, or an error
        string if the transfer is not valid.
        """
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
        for name in names:
            if name not in self.items:
                return f"Item '{number_text(name)}' does not exist"
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
        """Transfer the sibling items `names`, with their children, to
        `target`, a collection of the same type, at a place there.

        The items go `place` ("", "before" or "after") the item or number
        `word` of `target` (see `plan_place()`), in order.  Each item keeps
        the rest of its tag if it is free in `target`, or else gets a new
        one as `create` does; its `Details.md` and `Summary.md` headings
        are fixed, and the transfer is added to the "moves" list of its
        `.item.json`.  Both collections are renumbered to leave no gaps.
        The plan is first written to `.transfer.json` (see
        `do_transfer()`), so that an interrupted transfer is finished the
        next time a collection is loaded.  Returns each transferred item
        with its old tag, or an error string on failure.
        """
        first: tuple[int, ...] | str = self.check_transfer(
            names, target, place, word
        )
        if isinstance(first, str):
            return first
        planned: (
            tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]
            | str
        ) = target.plan_place([], place, first, len(names))
        if isinstance(planned, str):  # pragma: no cover
            # `check_transfer()` checked the place.
            return planned
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
        used: set[str] = {item.tag for item in target.items.values()}
        records: list[dict[str, str]] = []
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
        moved: set[tuple[int, ...]] = {item.name for item, _ in moving}
        source_names: dict[tuple[int, ...], tuple[int, ...]] = (
            self.gap_free_names(
                name for name in self.items if name not in moved
            )
        )
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
        for item, _ in moving:
            del self.items[item.name]
            del self.directories[item.name]
        self.apply_renames(source_names)
        target.apply_renames(target_names)
        transferred: list[tuple[str, Item]] = []
        for (item, new_name), record in zip(moving, records, strict=True):
            item.name = new_name
            item.tag = record["tag"]
            item.updated = stamp
            target.items[new_name] = item
            target.directories[new_name] = (
                target.items_directory / record["new"]
            )
            transferred.append((record["old_tag"], item))
        return transferred

    # Method `Items.set_state()`:
    def set_state(
        self, name: tuple[int, ...], state: str, recursive: bool = False
    ) -> list[Item] | str:
        """Set the state of item `name`, and its children if `recursive`.

        An item already in `state` is left unchanged.  Otherwise its
        updated time is set to now and the change is added to its history.
        Returns the selected items, or an error string on failure.
        """
        states: tuple[str, ...] = self.collection_type.states
        if state not in states:
            return f"State '{state}' is not one of {', '.join(states)}"
        changed: list[Item] | str = self.select_items(name, recursive)
        if isinstance(changed, str):
            return changed
        if self.collection_type.has_sources and state == "Active":
            for item in changed:
                if not item.source or not self.copy_path(item).is_file():
                    tag: str = f"{self.prefix}{item.tag}"
                    return (
                        f"{tag} has no copy of a source to make Active; "
                        f"`ai_contexts {tag} source PATH` sets its source"
                    )
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
        return changed

    # Method `Items.set_priority()`:
    def set_priority(
        self, name: tuple[int, ...], priority: int | None
    ) -> Item | str:
        """Set the priority of item `name`, or remove it if None.

        The updated time is set to now.  Returns the item, or an error
        string on failure.
        """
        selected: list[Item] | str = self.select_items(name)
        if isinstance(selected, str):
            return selected
        item: Item = selected[0]
        item_directory: Path = self.directories[name]
        try:
            item.updated = update_item(
                item_directory, fields={"priority": priority}
            )
        except (OSError, ValueError) as error:
            return f"Unable to write '{item_directory / ITEM_FILE}': {error}"
        item.priority = priority
        return item

    # Method `Items.feature_command()`:
    def feature_command(self, command: str, arguments: list[str]) -> str:
        """Run `enable FEATURE` or `disable FEATURE`.

        FEATURE may be any unique prefix of a feature.  Returns an empty
        string on success, or an error string on failure.
        """
        found: list[str] = matches(arguments[0], FEATURES) if arguments else []
        if len(arguments) != 1 or len(found) != 1:
            return (
                f"Usage: ai_contexts COLLECTION {command} FEATURE, where "
                f"FEATURE is one of: {', '.join(FEATURES)}"
            )
        return self.set_feature(found[0], command == "enable")

    # Method `Items.set_source()`:
    def set_source(self, name: tuple[int, ...], path: Path) -> Item | str:
        """Make the file at `path` the source of rule `name`, and copy it.

        The source is kept relative to `root`, after the directories in
        `path` are resolved to real ones; the file name is kept, so a file
        that is a symbolic link is followed whenever it is read.  A copy
        of the old source is removed, and the copy is always replaced.
        Returns the rule, or an error string on failure.
        """
        selected: list[Item] | str = self.select_items(name)
        if isinstance(selected, str):
            return selected
        item: Item = selected[0]
        if not path.is_file():
            return f"'{path}' is not a file"
        if path.name in RESERVED_NAMES or path.name.startswith("."):
            return f"A source can not be named '{path.name}'"
        source: str = (
            Path(os.path.relpath(path.absolute().parent.resolve(), self.root))
            .joinpath(path.name)
            .as_posix()
        )
        item_directory: Path = self.directories[name]
        try:
            if item.source:
                self.copy_path(item).unlink(missing_ok=True)
            item.updated = update_item(
                item_directory,
                fields={"source": source, "sha256": None, "refreshed": None},
            )
        except (OSError, ValueError) as error:
            return (
                f"Unable to set the source of {self.prefix}{item.tag}: {error}"
            )
        item.source = source
        message: str = self.refresh_rule(item, force=True)
        if message.startswith("Unable"):
            return message
        return item

    # Method `Items.source_command()`:
    def source_command(self, arguments: list[str]) -> str:
        """Run `source NUMBER PATH`: set the source of a rule and copy it.

        Returns an empty string on success, or an error string on failure.
        """
        if len(arguments) != 2:
            return "Usage: ai_contexts COLLECTION source NUMBER PATH"
        name: tuple[int, ...] | str = self.resolve(arguments[0])
        if isinstance(name, str):
            return name
        changed: Item | str = self.set_source(name, Path(arguments[1]))
        if isinstance(changed, str):
            return changed
        self.show([changed])
        return ""

    # Method `Items.refresh_command()`:
    def refresh_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `refresh NUMBER`: copy a rule's source over its copy.

        A copy that was edited in place is only replaced if `ask` gets a
        yes answer.  Returns an empty string on success, or an error string
        on failure.
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
    def create_rules(self, place: str, word: str, paths: list[Path]) -> str:
        """Create a rule for each of `paths`, at a place (see `plan_place()`).

        The first rule goes at `word` (a number, or a number or tag with a
        `place`), and each of the others after the one before.  Each is
        titled from its file name and has its source set.  The rules are
        printed.  Returns an empty string on success, or an error string on
        failure.
        """
        created: list[Item] = []
        for path in paths:
            title: str = path.stem.replace("_", " ")
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
        self.show(created)
        return ""

    # Method `Items.type_command()`:
    def type_command(self, arguments: list[str]) -> str:
        """Run `type [TYPE]`: print or set the type of the collection.

        TYPE may be any unique prefix of a type.  The type can only be
        changed while the collection is empty, so that no item is left in
        a state that its type does not have.  Returns an empty string on
        success, or an error string on failure.
        """
        found: list[str] = matches(arguments[0], TYPES) if arguments else []
        if len(arguments) > 1 or (arguments and len(found) != 1):
            return (
                "Usage: ai_contexts COLLECTION type [TYPE], where TYPE is one "
                f"of: {', '.join(TYPES)}"
            )
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
        print(f"{name}: {self.collection_type_name}")
        return ""

    # Method `Items.priority_command()`:
    def priority_command(self, arguments: list[str]) -> str:
        """Run `priority NUMBER LEVEL`.

        Returns an empty string on success, or an error string on failure.
        """
        if not self.priority_enabled:
            name: str = self.items_directory.name
            return (
                f"Priority is not enabled for '{name}'; use "
                f"`ai_contexts {name} enable priority`"
            )
        if len(arguments) != 2:
            return "Usage: ai_contexts COLLECTION priority NUMBER LEVEL"
        number: tuple[int, ...] | str = self.resolve(arguments[0])
        if isinstance(number, str):
            return number
        priority: int | None | str = parse_priority(arguments[1])
        if isinstance(priority, str):
            return priority
        changed: Item | str = self.set_priority(number, priority)
        if isinstance(changed, str):
            return changed
        self.show([changed])
        return ""

    # Method `Items.create_command()`:
    def create_command(self, arguments: list[str]) -> str:
        """Run `create [before|after] NUMBER TITLE...`.

        In a collection with sources it is `create [before|after] NUMBER
        FILE...` (see `create_rules()`).

        Returns an empty string on success, or an error string on failure.
        """
        place: str = ""
        if arguments and arguments[0] in PLACES:
            place, arguments = arguments[0], arguments[1:]
        sources: bool = self.collection_type.has_sources
        if len(arguments) < 2:
            return (
                "Usage: ai_contexts COLLECTION create [before|after] NUMBER "
                + ("FILE..." if sources else "TITLE...")
            )
        if sources:
            paths: list[Path] | str = expand_files(arguments[1:])
            if isinstance(paths, str):
                return paths
            return self.create_rules(place, arguments[0], paths)
        result: Item | str = self.create_item(
            arguments[0], " ".join(arguments[1:]), place
        )
        return result if isinstance(result, str) else ""

    # Method `Items.move_command()`:
    def move_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `move NUMBER [before|after] NUMBER`.

        A valid move may first ask to continue (see `confirm_snapshot()`).
        Prints the renumbered items.  Returns an empty string on success,
        or an error string on failure.
        """
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
        if not self.confirm_snapshot(ask):
            return "Not moved"
        renumbered: dict[str, Item] | str = self.move_items(
            names, place, target
        )
        if isinstance(renumbered, str):
            return renumbered
        error: str = self.note_move_or_rename()
        if error:
            return error
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

        COLLECTION is one of `collections`, by any unique prefix.  Without
        a place, the items go to the next free top-level number.  A valid
        transfer may first ask to continue (see `confirm_snapshot()`).
        Prints the transferred items and the renumbered ones, then offers
        to change their old tags in the project's `.md` files (see
        `update_references()`).  Returns an empty string on success, or an
        error string on failure.
        """
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
        if not self.confirm_snapshot(ask):
            return "Not transferred"
        before: dict[int, tuple[str, Item]] = {
            id(item): (item.number, item)
            for collection in (self, target)
            for item in collection.items.values()
        }
        transferred: list[tuple[str, Item]] | str = self.transfer_items(
            names, target, place, word
        )
        if isinstance(transferred, str):
            return transferred
        error: str = self.note_move_or_rename() or target.note_move_or_rename()
        if error:
            return error
        print("Transferred (old tag first):")
        target.show(
            [item for _, item in transferred],
            old_numbers=[old_tag for old_tag, _ in transferred],
        )
        moved: set[int] = {id(item) for _, item in transferred}
        for collection in (self, target):
            renumbered: dict[str, Item] = {
                before[id(item)][0]: item
                for item in collection.list_items()
                if id(item) not in moved and before[id(item)][0] != item.number
            }
            if renumbered:
                print(f"In {collection.items_directory.name}:")
                collection.show_renumbered(renumbered)
        return self.update_references(
            {
                old_tag: f"{target.prefix}{item.tag}"
                for old_tag, item in transferred
            },
            ask,
        )

    # Method `Items.show_command()`:
    def show_command(self, arguments: list[str]) -> str:
        """Run `show NUMBER`: print an item's details and its `Details.md`.

        Returns an empty string on success, or an error string on failure.
        """
        if len(arguments) != 1:
            return "Usage: ai_contexts COLLECTION show NUMBER"
        name: tuple[int, ...] | str = self.resolve(arguments[0])
        if isinstance(name, str):
            return name
        if name not in self.items:
            return f"Item '{number_text(name)}' does not exist"
        item: Item = self.items[name]
        item_directory: Path = self.directories[name]
        try:
            metadata: dict[str, object] = read_item(item_directory)
            details: str = read_file(item_directory / "Details.md")
        except (OSError, ValueError) as error:
            return f"Unable to read item '{item.number}': {error}"
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
        if self.collection_type.has_sources:
            lines += [
                f"Source:    {item.source or '-'}",
                f"SHA-256:   {metadata.get('sha256', '-')}",
                (
                    "Refreshed: "
                    f"{local_time(str(metadata.get('refreshed', '')))}"
                ),
            ]
        lines += [
            f"Created:   {local_time(item.created)}",
            f"Updated:   {local_time(item.updated)}",
            f"Directory: {item_directory.parent.name}/{item_directory.name}",
            "History:",
        ]
        history: object = metadata.get("history")
        for change in history if isinstance(history, list) else []:
            if isinstance(change, dict):
                lines.append(
                    f"  {local_time(str(change.get('time', ''))):<16}  "
                    f"{change.get('state', '?')}"
                )
        moves: object = metadata.get("moves")
        if isinstance(moves, list) and moves:
            lines.append("Transfers:")
            lines += [
                f"  {local_time(str(move.get('time', ''))):<16}  "
                f"{move.get('from', '?')} -> {move.get('to', '?')}"
                for move in moves
                if isinstance(move, dict)
            ]
        print("\n".join(lines) + "\n")
        print(details, end="")
        return ""

    # Method `Items.show_renumbered()`:
    def show_renumbered(self, renumbered: dict[str, Item]) -> None:
        """Print the `renumbered` items, keyed by their old numbers."""
        if renumbered:
            print("Renumbered (old number first):")
            self.show(list(renumbered.values()), old_numbers=list(renumbered))

    # Method `Items.list_command()`:
    def list_command(self, arguments: list[str]) -> str:
        """Run `list [-a] [-l] [NUMBER]`.

        Closed and Rejected items are left out, unless `-a` is given or it
        is the item
        NUMBER itself, and a note says how many.  Returns an empty string
        on success, or an error string on failure.
        """
        long: bool = False
        everything: bool = False
        numbers: list[str] = []
        for argument in arguments:
            if argument in ("-l", "--long"):
                long = True
            elif argument in ("-a", "--all"):
                everything = True
            else:
                numbers.append(argument)
        if len(numbers) > 1:
            return "Usage: ai_contexts COLLECTION list [-a] [-l] [NUMBER]"
        name: tuple[int, ...] | str = (
            self.resolve(numbers[0]) if numbers else ()
        )
        if isinstance(name, str):
            return name
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
        if self.priority_enabled:
            listed.sort(
                key=lambda item: (
                    item.priority is None,
                    item.priority or 0,
                    item.name,
                )
            )
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

        Returns an empty string on success, or an error string on failure.
        """
        parsed: tuple[tuple[int, ...], bool] | str = parse_recursive(
            command, arguments, self.resolve
        )
        if isinstance(parsed, str):
            return parsed
        name, recursive = parsed
        changed: list[Item] | str = self.set_state(
            name, STATE_COMMANDS[command], recursive
        )
        if isinstance(changed, str):
            return changed
        self.show(changed)
        return ""

    # Method `Items.rename_command()`:
    def rename_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `rename NUMBER to TITLE...`.

        A rename of an existing item to a usable title may first ask to
        continue (see `confirm_snapshot()`).  Returns an empty string on
        success, or an error string on failure.
        """
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
        if not self.confirm_snapshot(ask):
            return "Not renamed"
        old_tag: str = f"{self.prefix}{self.items[name].tag}"
        renamed: Item | str = self.rename_item(name, title)
        if isinstance(renamed, str):
            return renamed
        error: str = self.note_move_or_rename()
        if error:
            return error
        self.show([renamed])
        new_tag: str = f"{self.prefix}{renamed.tag}"
        if new_tag == old_tag:
            return ""
        return self.update_references({old_tag: new_tag}, ask)

    # Method `Items.update_references()`:
    def update_references(
        self, tags: dict[str, str], ask: Callable[[str], str]
    ) -> str:
        """Offer to change each old tag of `tags` to its new tag in the
        project's `.md` files, in one pass.

        The files are found by `tag_references()` in the directory that
        holds the collections, and are only changed if `ask` gets a yes.
        Returns an empty string on success, or an error string on failure.
        """
        root: Path = self.items_directory.parent
        paths: list[Path] = sorted(
            {
                path
                for old_tag in tags
                for path in tag_references(root, old_tag)
            }
        )
        if not paths:
            return ""
        print("The following `.md` files have tags that need to be renamed:")
        for path in paths:
            print(f"  {path.relative_to(root)}")
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
        # One pattern changes every tag at once, so that a new tag is never
        # changed again as another's old tag.
        pattern: re.Pattern[str] = re.compile(
            "|".join(tag_pattern(old_tag).pattern for old_tag in tags)
        )
        for path in paths:
            try:
                write_file(
                    path,
                    pattern.sub(
                        lambda found: tags[found.group(0)], read_file(path)
                    ),
                )
            except OSError as error:
                return f"Unable to update '{path}': {error}"
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

        Prints the deleted items and the renumbered ones.  Returns an
        empty string on success, or an error string on failure.
        """
        recursive: bool = False
        words: list[str] = []
        for argument in arguments:
            if argument in ("-r", "--recursive"):
                recursive = True
            else:
                words.append(argument)
        if len(words) != 1:
            return "Usage: ai_contexts COLLECTION delete [-r] NUMBER"
        names: list[tuple[int, ...]] | str = self.resolve_range(words[0])
        if isinstance(names, str):
            return names
        result: tuple[list[Item], dict[str, Item]] | str = self.delete_items(
            names, recursive, ask
        )
        if isinstance(result, str):
            return result
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
        """Run `NAME create` to create the collection directory `name`.

        It goes next to the existing collection `directories`, or else in
        the current directory, after `ask` gets a yes answer.  Returns 0
        for success and 1 for failure.
        """
        if name in ("", ".", "..") or Path(name).name != name:
            print(f"Invalid collection name '{name}'", file=sys.stderr)
            return 1
        parent: Path = directories[0].parent if directories else Path.cwd()
        path: Path = parent / name
        if path.exists():
            print(f"'{path}' already exists", file=sys.stderr)
            return 1
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
        try:
            answer: str = ask(f"Create collection directory '{path}'? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().casefold() not in ("y", "yes"):
            print("Not created", file=sys.stderr)
            return 1
        created: Items = Items(path)
        if created.error:
            return 1
        print(f"Created '{path}'")
        collections: list[Items] = [
            Items(directory) for directory in directories
        ]
        error: str = write_startup(
            [
                collection
                for collection in [created, *collections]
                if not collection.error
            ]
        )
        if error:
            print(error, file=sys.stderr)
            return 1
        return 0

    # Method `Items.list_collections()`:
    @staticmethod
    def list_collections() -> int:
        """Run `ai_contexts` with no arguments: list the collections.

        Prints how many collections were found and where, a numbered line
        for each with its tag prefix and how many items it has in each
        state, and a pointer to the help.  Returns 0.
        """
        directories: list[Path] = find_collections(Path.cwd())
        where: str = f" in '{directories[0].parent}'" if directories else ""
        print(
            f"{len(directories)} collection"
            f"{'' if len(directories) == 1 else 's'} found{where}"
            f"{':' if directories else ''}"
        )
        width: int = max((len(path.name) for path in directories), default=0)
        number_width: int = len(str(len(directories)))
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

        `ask` is called with a yes/no question before a new collection is
        created, and returns the answer.  Returns 0 for success and 1 for
        failure.
        """
        if not arguments:
            return Items.list_collections()
        if arguments[0] in ("-h", "--help"):
            print(HELP)
            return 0
        if arguments == ["--test"]:  # pragma: no cover
            # The tests are in `ai_contexts_test.py`, next to this file (even
            # when ai_contexts is run through a symbolic link).  They are not
            # run from here when coverage is measured, which runs
            # `ai_contexts_test.py` itself.
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import ai_contexts_test

            return ai_contexts_test.test()
        error: str = ""
        directories: list[Path] = find_collections(Path.cwd())
        names: list[str] = [directory.name for directory in directories]
        found: list[str] = matches(arguments[0], names)
        tag: str = ""
        if not found and tag_collection(arguments[0], names):
            found = [tag_collection(arguments[0], names)]
            tag = arguments[0]
        # A collection's type decides its commands; when there is no such
        # collection, every command is allowed (for `ai_contexts NAME create`).
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
            error = (
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
        if error:
            print(error, file=sys.stderr)
            return 1
        collections: list[Items] = [
            Items(directory) for directory in directories
        ]
        items: Items = collections[names.index(found[0])]
        if items.error:
            return 1
        rest: list[str] = ([tag] if tag else []) + arguments[2:]
        match matched[0]:
            case "help":
                print(HELP)
            case "create":
                error = items.create_command(rest)
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
                error = items.source_command(rest)
            case "refresh":
                error = items.refresh_command(rest, ask)
            case "enable" | "disable":
                error = items.feature_command(matched[0], rest)
            case state_command:
                error = items.state_command(state_command, rest)
        if not error:
            loaded: list[Items] = [
                collection
                for collection in collections
                if not collection.error
            ]
            error = write_startup(loaded) or write_active_rules(loaded)
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
    `Details.md` of every item that is not Closed and the `Context.md` of
    every Open or Reference item (the TASKS items first, then those of the
    other `collections` in order), then the `Summary.md` (or `Details.md`
    if the summary is empty) of the `CLOSED_SUMMARIES` (or the number in
    the `SUMMARIES_VARIABLE` environment variable) most recently Closed
    items, newest first, and finally `Closed.md` if there are older Closed
    items (see `write_closed()`).  Returns an empty string on success, or
    an error string on failure.
    """
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
    lines: list[str] = []
    closed: list[tuple[str, str, str, Path, str]] = []
    for collection in [startup] + [
        collection for collection in collections if collection is not startup
    ]:
        collection_type: CollectionType = collection.collection_type
        if not collection_type.in_startup:
            continue
        for item in collection.list_items():
            item_directory: Path = collection.directories[item.name]
            relative: str = Path(
                os.path.relpath(item_directory, startup.items_directory)
            ).as_posix()
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
            file_names: tuple[str, ...] = ("Details.md",)
            if item.state in collection_type.context_states:
                file_names += ("Context.md",)
            for file_name in file_names:
                if (item_directory / file_name).is_file():
                    lines.append(f"@{relative}/{file_name}")
    limit: int = CLOSED_SUMMARIES
    with contextlib.suppress(ValueError):
        limit = int(os.environ.get(SUMMARIES_VARIABLE, limit))
    closed.sort(key=lambda entry: entry[0], reverse=True)
    for _, _, _, item_directory, relative in closed[:limit]:
        summary_file: str = (
            "Summary.md" if has_summary(item_directory) else "Details.md"
        )
        lines.append(f"@{relative}/{summary_file}")
    older: list[tuple[str, str]] = [
        (tag, title) for _, tag, title, _, _ in closed[limit:]
    ]
    if older:
        lines.append("@Closed.md")
    startup_path: Path = startup.items_directory / "Startup.md"
    try:
        write_file(startup_path, "".join(f"{line}\n" for line in lines))
    except OSError as error:
        return f"Unable to write '{startup_path}': {error}"
    return write_closed(startup.items_directory / "Closed.md", older)


# Function `do_transfer()`:
def do_transfer(directory: Path, plan: dict[str, object], phase: int) -> str:
    """Do the transfer `plan` from the collection `directory`, from `phase`.

    The plan names the target collection (a sibling of `directory`), the
    time, the "items" (each with the `TRANSFER_KEYS`) and the renames of
    the renumberings of the source and the target (as in
    `.renumber.json`).  Phase 1 moves the item directories to temporary
    names in the target, phase 2 renumbers the source, phase 3 renumbers
    the target to make room, and phase 4 fixes each item's headings and
    `.item.json` and gives it its new name.  Each step is skipped if it
    has already been done, and `.transfer.json` in `directory` records the
    plan and its phase until the end, when it is removed.  Returns an
    empty string on success, or an error string on failure.
    """
    marker: Path = directory / TRANSFER_FILE
    target: Path = directory.parent / str(plan["target"])
    stamp: str = str(plan["time"])
    items: list[dict[str, str]] = plan_list(plan, "items", TRANSFER_KEYS)
    limit: str = os.environ.get(INTERRUPT_VARIABLE, "")
    steps: list[int] = [0]

    def step() -> None:
        steps[0] += 1
        if limit.isdecimal() and steps[0] > int(limit):
            raise RenumberInterrupted

    def save(next_phase: int) -> None:
        write_file(
            marker, json.dumps({**plan, "phase": next_phase}, indent=2) + "\n"
        )

    try:
        save(phase)
        if phase <= 1:
            for item in items:
                if (directory / item["old"]).exists() and not (
                    target / item["temporary"]
                ).exists():
                    step()
                    (directory / item["old"]).rename(
                        target / item["temporary"]
                    )
            save(2)
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
        for item in items:
            temporary: Path = target / item["temporary"]
            if not temporary.exists():
                continue
            step()
            details_path: Path = temporary / "Details.md"
            details: str = read_file(details_path)
            prefix: str = f"# {item['old_number']} "
            if details.startswith(prefix):
                write_file(
                    details_path,
                    f"# {item['new_number']} {details[len(prefix) :]}",
                )
            if item["summary"]:
                write_summary_heading(
                    temporary, summary_heading(item["new_tag"], item["title"])
                )
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
            temporary.rename(target / item["new"])
        marker.unlink()
    except (OSError, ValueError) as error:
        return (
            f"Unable to transfer items from '{directory}' to '{target}': "
            f"{error}"
        )
    return ""


# Function `plan_list()`:
def plan_list(
    plan: dict[str, object], key: str, keys: tuple[str, ...]
) -> list[dict[str, str]]:
    """Return the list `key` of `plan`, each entry with the `keys`.

    Raises a `ValueError` if it is not a list of JSON objects with them.
    """
    entries: object = plan.get(key)
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) and all(name in entry for name in keys)
        for entry in entries
    ):
        raise ValueError(f"'{key}' is not a list of {', '.join(keys)}")
    return [{name: str(entry[name]) for name in keys} for entry in entries]


# Function `recover_transfers()`:
def recover_transfers(parent: Path) -> None:
    """Finish every interrupted transfer between the collections in `parent`.

    This is done before any collection is loaded, since a collection in
    the middle of a transfer can have gaps that must not be "fixed".  The
    recovery, or a failure to recover, is reported to stderr.
    """
    try:
        directories: list[Path] = sorted(parent.iterdir())
    except OSError:
        return
    for directory in directories:
        marker: Path = directory / TRANSFER_FILE
        if not (directory / COLLECTION_FILE).is_file() or not marker.exists():
            continue
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
    """Do the `renames` of a renumbering in `directory`, from `phase`.

    Phase 1 renames the old directories to temporary names, phase 2
    renames those to the new names, and phase 3 rewrites the headings.
    Each step is skipped if it has already been done, and
    `.renumber.json` records the phase until the end, when it is
    removed.  Returns an empty string on success, or an error string
    on failure.
    """
    marker: Path = directory / RENUMBER_FILE
    limit: str = os.environ.get(INTERRUPT_VARIABLE, "")
    steps: list[int] = [0]

    def step() -> None:
        steps[0] += 1
        if limit.isdecimal() and steps[0] > int(limit):
            raise RenumberInterrupted

    def path(rename: dict[str, str], key: str) -> Path:
        return directory / rename[key]

    try:
        write_file(
            marker,
            json.dumps({"phase": phase, "renames": renames}, indent=2) + "\n",
        )
        if phase == 1:
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
        for rename in renames:
            if path(rename, "temporary").exists():
                step()
                path(rename, "temporary").rename(path(rename, "new"))
        for rename in renames:
            details_path: Path = path(rename, "new") / "Details.md"
            details: str = read_file(details_path)
            prefix: str = f"# {rename['old_number']} "
            if details.startswith(prefix):
                step()
                write_file(
                    details_path,
                    f"# {rename['new_number']} {details[len(prefix) :]}",
                )
        marker.unlink()
    except OSError as error:
        return f"Unable to renumber items in '{directory}': {error}"
    return ""


# Function `write_active_rules()`:
def write_active_rules(collections: list["Items"]) -> str:
    """Write `Active_Rules.md` into each collection with sources.

    Every line is an `@` import, relative to the collection, of the copy of
    an Active item's source, in number order, so that adding
    `@RULES/Active_Rules.md` to `CLAUDE.md` loads them.  Returns an empty
    string on success, or an error string on failure.
    """
    for collection in collections:
        if not collection.collection_type.has_sources:
            continue
        lines: list[str] = [
            f"@{collection.directories[item.name].name}/"
            f"{collection.copy_path(item).name}\n"
            for item in collection.list_items()
            if item.state == "Active"
            and item.source
            and collection.copy_path(item).is_file()
        ]
        path: Path = collection.items_directory / ACTIVE_RULES
        try:
            write_file(path, "".join(lines))
        except OSError as error:
            return f"Unable to write '{path}': {error}"
    return ""


# Function `closed_time()`:
def closed_time(item: "Item", item_directory: Path) -> str:
    """Return when `item` was last Closed, from its state history.

    Returns its updated time if the history does not say.
    """
    with contextlib.suppress(OSError, ValueError):
        history: object = read_item(item_directory).get("history")
        for change in reversed(history if isinstance(history, list) else []):
            if (
                isinstance(change, dict)
                and change.get("state") in FINISHED_STATES
            ):
                return str(change.get("time", item.updated))
    return item.updated


# Function `write_closed()`:
def write_closed(closed_path: Path, older: list[tuple[str, str]]) -> str:
    """Write `Closed.md`, or remove it if there are no `older` items.

    `older` holds the tag and title of each Closed item whose summary is
    not in `Startup.md`, newest first.  Returns an empty string on
    success, or an error string on failure.
    """
    lines: list[str] = [
        "# Older Closed and Rejected Items",
        "",
        "<!-- Written by ai_contexts; do not edit. -->",
        "",
        "These items are only listed by tag and title; `ai_contexts TAG",
        "show` shows the rest.",
        "",
    ] + [f"- `{tag}` {title}" for tag, title in older]
    try:
        if older:
            write_file(closed_path, "\n".join(lines) + "\n")
        else:
            closed_path.unlink(missing_ok=True)
    except OSError as error:
        return f"Unable to write '{closed_path}': {error}"
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

    The priority is only printed if `priority`, with "-" for none.  Tags
    are printed with `prefix`.  If `long`, the created and updated times
    are also printed in the local time zone.  If `old_numbers` is given,
    each line starts with the item's old number and "->".
    """
    old_width: int = max((len(old) for old in old_numbers or []), default=0)
    width: int = max((len(item.number) for item in items), default=0)
    tags: dict[tuple[int, ...], str] = {
        item.name: f"{prefix}{item.tag}" if item.tag else "" for item in items
    }
    tag_width: int = max((len(tag) for tag in tags.values()), default=0)
    state_width: int = max(len(state) for state in ALL_STATES)
    time_width: int = len("YYYY-MM-DD HH:MM")
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
