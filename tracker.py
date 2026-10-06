#!/usr/bin/env python3
"""A general purpose command line tool for tracking items."""

import contextlib
import json
import os
import re
import shutil
import string
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

HELP: str = """Usage: tracker COLLECTION COMMAND [ARGUMENTS...]
       tracker TAG COMMAND [ARGUMENTS...]
                               Same as `tracker COLLECTION COMMAND TAG ...`
                               for the collection of TAG (e.g. I.dbzib)
       tracker NAME create     Create the collection directory NAME
       tracker --test          Run the self tests in a temporary directory
       tracker [-h | --help]   Print this help message

A COLLECTION is a directory containing a `.tracker.json` file.  They are
found in the current directory, or else the nearest parent directory that
has any.  COLLECTION and COMMAND may be shortened to any unique prefix, in
any case (e.g. `tracker t cl 2` closes item 2 in TASKS).  A new collection
is created, after asking, next to the existing ones (or else in the
current directory) and is named exactly as typed.

Commands:
  create PLACE TITLE...   Create an item at PLACE (see below)
  move NUMBER PLACE       Move an item, with its children, to PLACE.
                          NUMBER may be a range of siblings, like 1.2.5-6
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
  priority NUMBER LEVEL   Set the item priority: 0 (catastrophic), 1 (high),
                          2 (medium), 3 (low), or - for none
  enable FEATURE          Enable a collection feature (only: priority)
  disable FEATURE         Disable a collection feature
  help                    Print this help message

Options:
  -r, --recursive         Also apply to all of the child items
  -a, --all               Also list the Closed items
  -l, --long              Also list the created and updated times

Items are numbered without gaps: if 1.3 exists, so do 1.1 and 1.2.  A
PLACE is one of:
  NUMBER          The next free number of a level (e.g. 1.3 after 1.2, or
                  2.1.1 for the first child of 2.1)
  before NUMBER   Where item NUMBER is; it and its later siblings move
                  down one
  after NUMBER    Just after item NUMBER; its later siblings move down one
Deleting or moving items moves the later siblings (and their children) up
to close the gap.  There is no undo.  Before a move or rename, if the last
one in the collection was more than an hour ago, tracker recommends taking
a version control snapshot (e.g. `git commit`) first, and asks whether to
continue.

Item states are: Pending, Open, Reference, Suspended, Closed
New items are created Pending.  Open items are being worked on.  Reference
items are not, but like Open items their Context.md is in Startup.md.
Each item also has a Summary.md, written before it is closed.  For the 50
most recently closed items, Startup.md has their Summary.md (or Details.md
if the summary is empty); older closed items are listed by tag and title
in a generated TASKS/Closed.md.

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
    "Pending", "Open", "Reference", "Suspended", "Closed"
)

# The states whose `Context.md` is imported by `Startup.md`.
CONTEXT_STATES: tuple[str, ...] = ("Open", "Reference")

# The hidden JSON file in each item directory that holds its metadata.
ITEM_FILE: str = ".item.json"

# The hidden file that held the state of an item in the old format.
OLD_STATUS_FILE: str = ".status"

# The hidden JSON file that marks a directory as a collection of items.
COLLECTION_FILE: str = ".tracker.json"

# The hidden JSON file that holds a renumbering while it is being done, so
# that an interrupted renumbering can be finished.
RENUMBER_FILE: str = ".renumber.json"

# The environment variable with which the test suite interrupts a
# renumbering after that many steps.
INTERRUPT_VARIABLE: str = "TRACKER_TEST_RENUMBER_INTERRUPT"

# The commands whose first argument is an item, so that `tracker TAG
# COMMAND ...` can be used.
TAG_COMMANDS: frozenset[str] = frozenset(
    {
        "rename", "delete", "list", "show", "pending", "open", "reference",
        "suspend", "close", "priority", "move",
    }
)

# The number of most recently closed items whose `Summary.md` is in
# `Startup.md`;
# the test suite can change it with the environment variable named by
# `SUMMARIES_VARIABLE`.
CLOSED_SUMMARIES: int = 50
SUMMARIES_VARIABLE: str = "TRACKER_TEST_CLOSED_SUMMARIES"

# The keys of each rename in `.renumber.json`.
RENAME_KEYS: tuple[str, ...] = (
    "old", "temporary", "new", "old_number", "new_number"
)

# The collection that holds `Startup.md` for all of the collections.
STARTUP_COLLECTION: str = "TASKS"

# The priority levels, from catastrophic (0) to low (3).
PRIORITIES: tuple[int, ...] = (0, 1, 2, 3)

# The seconds after a move or rename before the next one reminds the user
# to take a version control snapshot.  The test suite can change it with
# the environment variable named by `DELAY_VARIABLE`.
MOVE_RENAME_DELAY_SECONDS: float = 3600.0
DELAY_VARIABLE: str = "TRACKER_TEST_MOVE_RENAME_DELAY_SECONDS"

# The places relative to an existing item.
PLACES: tuple[str, ...] = ("before", "after")

# A stand-in name for an item that is about to be created.
NEW_ITEM: tuple[int, ...] = (0,)

# The features that can be enabled for a collection in `.tracker.json`.
FEATURES: tuple[str, ...] = ("priority",)

# The words that are left out of a tag.
TAG_IGNORED_WORDS: frozenset[str] = frozenset({"a", "an", "of", "the"})

# The commands, and the command that each one runs.
COMMANDS: dict[str, str] = {
    "create": "create",
    "rename": "rename",
    "delete": "delete",
    "list": "list",
    "ls": "list",
    "pending": "pending",
    "open": "open",
    "reference": "reference",
    "suspend": "suspend",
    "close": "close",
    "priority": "priority",
    "move": "move",
    "show": "show",
    "enable": "enable",
    "disable": "disable",
    "help": "help",
}


class RenumberInterrupted(Exception):
    """A renumbering interrupted by the test suite (`INTERRUPT_VARIABLE`)."""


def read_file(path: Path) -> str:
    """Return the contents of the UTF-8 text file at `path`."""
    return path.read_text(encoding="utf-8")


def write_file(path: Path, text: str) -> None:
    """Write `text` to `path` as a UTF-8 text file."""
    path.write_text(text, encoding="utf-8")


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


def write_item(item_directory: Path, metadata: dict[str, object]) -> None:
    """Write the `metadata` into the `.item.json` of `item_directory`."""
    text: str = json.dumps(metadata, indent=2)
    write_file(item_directory / ITEM_FILE, f"{text}\n")


def utc_stamp(seconds: float) -> str:
    """Return `seconds` since the epoch as a UTC timestamp string.

    The timestamp is ISO 8601, like "2026-10-05T21:35:00Z".
    """
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def find_collections(start: Path) -> list[Path]:
    """Return the collection directories nearest to `start`, sorted.

    `start` and then each of its parents is searched for sub-directories
    that contain a `.tracker.json` file.  The ones in the first directory
    that has any are returned, or an empty list if none are found.
    """
    for directory in (start, *start.parents):
        try:
            found: list[Path] = sorted(
                path
                for path in directory.iterdir()
                if (path / COLLECTION_FILE).is_file()
            )
        except OSError:
            continue
        if found:
            return found
    return []


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


def unique_tag(base: str, used: Iterable[str]) -> str:
    """Return `base`, or `base` plus the lowest number from 2 not `used`."""
    used_tags: set[str] = set(used)
    if base not in used_tags:
        return base
    number: int = 2
    while f"{base}{number}" in used_tags:
        number += 1
    return f"{base}{number}"


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


def number_text(name: tuple[int, ...]) -> str:
    """Return `name` as period separated numbers, like "1.2.3"."""
    return ".".join(str(part) for part in name)


def tag_prefix(collection_name: str) -> str:
    """Return the tag prefix of a collection, like "T." for "TASKS"."""
    return f"{collection_name[:1].upper()}."


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


def summary_heading(tag: str, title: str) -> str:
    """Return the first line of an item's `Summary.md`."""
    return f"# Summary of `{tag}` {title}"


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


def has_summary(item_directory: Path) -> bool:
    """Return whether the item's `Summary.md` says more than its heading."""
    try:
        text: str = read_file(item_directory / "Summary.md")
    except OSError:
        return False
    if text.startswith("# Summary of "):
        text = text.partition("\n")[2]
    return bool(text.strip())


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


def tag_pattern(tag: str) -> re.Pattern[str]:
    """Return a pattern that finds the whole `tag` in text."""
    return re.compile(rf"(?<![\w.]){re.escape(tag)}(?!\w)")


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
        return f"Usage: tracker COLLECTION {command} [-r] NUMBER"
    name: tuple[int, ...] | str = resolve(numbers[0])
    if isinstance(name, str):
        return name
    return name, recursive


@dataclass
class Item:
    """A single item."""

    name: tuple[int, ...]
    title: str
    state: str = "Pending"
    created: str = ""
    updated: str = ""
    tag: str = ""
    priority: int | None = None

    def __post_init__(self) -> None:
        """Ensure that the name and state are valid.

        The name must be a non-empty tuple of positive integers and the
        state must be one of `STATES`.  Raises a `ValueError` if not.
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
        if self.state not in STATES:
            raise ValueError(
                f"Item state {self.state!r} is not one of "
                f"{', '.join(STATES)}"
            )

    @property
    def number(self) -> str:
        """Return the name as period separated numbers, like "1.2.3"."""
        return ".".join(str(part) for part in self.name)


class Items:
    """A collection of items."""

    def __init__(self, items_directory: Path) -> None:
        """Initialize the collection of items in `items_directory`.

        Creates `items_directory` and its `.tracker.json` file if they are
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
                write_file(collection_path, "{}\n")
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
                else:
                    self.error = (
                        f"Unable to read '{collection_path}': "
                        "it is not a JSON object"
                    )
        if self.error:
            print(self.error, file=sys.stderr)
        else:
            self.recover_renumber()
            self.load_items()

    @property
    def prefix(self) -> str:
        """Return the tag prefix of this collection, like "T."."""
        return tag_prefix(self.items_directory.name)

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

    @property
    def priority_enabled(self) -> bool:
        """Return whether priority is enabled for this collection."""
        return self.settings.get("priority") is True

    def save_settings(self, settings: dict[str, object]) -> str:
        """Write `settings` to `.tracker.json` and keep them.

        Returns an empty string on success, or an error string on failure.
        """
        collection_path: Path = self.items_directory / COLLECTION_FILE
        try:
            write_file(collection_path, json.dumps(settings, indent=2) + "\n")
        except OSError as error:
            return f"Unable to write '{collection_path}': {error}"
        self.settings = settings
        return ""

    def set_feature(self, feature: str, enabled: bool) -> str:
        """Enable or disable `feature` in `.tracker.json`.

        Returns an empty string on success, or an error string on failure.
        """
        return self.save_settings({**self.settings, feature: enabled})

    def confirm_snapshot(self, ask: Callable[[str], str]) -> bool:
        """Before a move or rename, recommend a version control snapshot.

        If there has been no move or rename in this collection for
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
                f"No move or rename in '{self.items_directory.name}' for "
                + (
                    "over an hour"
                    if delay == MOVE_RENAME_DELAY_SECONDS
                    else f"over {delay:g} seconds"
                )
                + "; consider taking a version control "
                "snapshot (e.g. `git commit`) before moving or renaming "
                "items.",
                file=sys.stderr,
            )
            try:
                answer: str = ask("Continue? Yes(y) or No(n). ")
            except EOFError:
                answer = ""
            return answer.strip().casefold() in ("y", "yes")
        return True

    def note_move_or_rename(self) -> str:
        """Save the time of a move or rename in `.tracker.json`.

        Returns an empty string on success, or an error string on failure.
        """
        return self.save_settings(
            {
                **self.settings,
                "last_move_or_rename": utc_stamp(time.time()),
            }
        )

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
                title = heading[len(prefix):].strip()
            priority: object = metadata.get("priority")
            try:
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
                )
            except ValueError as error:
                print(f"Skipping '{item_directory}': {error}", file=sys.stderr)
            else:
                self.directories[name] = item_directory
        self.add_missing_tags()
        self.add_missing_summaries()
        self.fix_gaps()
        self.check_items()

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

    def gap_free_names(self) -> dict[tuple[int, ...], tuple[int, ...]]:
        """Return the new name of each item whose name must change.

        Items keep their order.  An item whose parent is missing becomes
        a child of its nearest existing ancestor.
        """
        new_names: dict[tuple[int, ...], tuple[int, ...]] = {}
        counts: dict[tuple[int, ...], int] = {}
        for name in sorted(self.items):
            parent: tuple[int, ...] = next(
                (
                    name[:length]
                    for length in range(len(name) - 1, 0, -1)
                    if name[:length] in self.items
                ),
                (),
            )
            new_parent: tuple[int, ...] = new_names[parent] if parent else ()
            counts[new_parent] = counts.get(new_parent, 0) + 1
            new_names[name] = new_parent + (counts[new_parent],)
        return {old: new for old, new in new_names.items() if old != new}

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
        error: str = self.do_renumber(renames, 1)
        if error and not (self.items_directory / RENUMBER_FILE).exists():
            return error
        # Even after a failure, the items are where the plan puts them,
        # since the next load finishes the plan.
        moving: list[Item] = [self.items[old] for old in sorted(new_names)]
        for item in moving:
            del self.items[item.name]
            del self.directories[item.name]
        for item, rename in zip(moving, renames, strict=True):
            item.name = new_names[item.name]
            self.items[item.name] = item
            self.directories[item.name] = (
                self.items_directory / rename["new"]
            )
        return error

    def do_renumber(self, renames: list[dict[str, str]], phase: int) -> str:
        """Do the `renames` of a renumbering, starting at `phase`.

        Phase 1 renames the old directories to temporary names, phase 2
        renames those to the new names, and phase 3 rewrites the headings.
        Each step is skipped if it has already been done, and
        `.renumber.json` records the phase until the end, when it is
        removed.  Returns an empty string on success, or an error string
        on failure.
        """
        marker: Path = self.items_directory / RENUMBER_FILE
        limit: str = os.environ.get(INTERRUPT_VARIABLE, "")
        steps: list[int] = [0]

        def step() -> None:
            steps[0] += 1
            if limit.isdecimal() and steps[0] > int(limit):
                raise RenumberInterrupted

        def path(rename: dict[str, str], key: str) -> Path:
            return self.items_directory / rename[key]

        try:
            write_file(
                marker,
                json.dumps({"phase": phase, "renames": renames}, indent=2)
                + "\n",
            )
            if phase == 1:
                for rename in renames:
                    if path(rename, "old").exists() and not path(
                        rename, "temporary"
                    ).exists():
                        step()
                        path(rename, "old").rename(path(rename, "temporary"))
                write_file(
                    marker,
                    json.dumps({"phase": 2, "renames": renames}, indent=2)
                    + "\n",
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
                        f"# {rename['new_number']} {details[len(prefix):]}",
                    )
            marker.unlink()
        except OSError as error:
            return (
                f"Unable to renumber items in '{self.items_directory}': "
                f"{error}"
            )
        return ""

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
            phase: int = int(plan["phase"])
            renames: list[dict[str, str]] = [
                {key: str(rename[key]) for key in RENAME_KEYS}
                for rename in plan["renames"]
            ]
        except (OSError, ValueError, TypeError, KeyError) as problem:
            error = f"Unable to read '{marker}': {problem!r}"
        else:
            error = self.do_renumber(renames, phase)
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

    def check_items(self) -> None:
        """Check the items each time the collection is loaded.

        What tracker maintains is fixed: the number in the `# N Title`
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
                        f"'# {item.number} TITLE' heading; `tracker "
                        f"{self.prefix}{item.tag} rename to TITLE` adds one"
                    )
                if clean_title(item.title) != item_directory.name.partition(
                    "_"
                )[2]:
                    messages.append(
                        f"{where}: its directory name does not match its "
                        f"title '{item.title}'; `tracker "
                        f"{self.prefix}{item.tag} rename to {item.title}` "
                        "fixes it"
                    )
                summary: str = summary_heading(
                    f"{self.prefix}{item.tag}", item.title
                )
                if (item_directory / "Summary.md").exists() and read_file(
                    item_directory / "Summary.md"
                ).partition("\n")[0] != summary:
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

    def add_missing_summaries(self) -> None:
        """Give an empty `Summary.md` to every item that does not have one.

        This is for items made before `Summary.md` existed.  A file that
        can not be written is reported to stderr.
        """
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

    def list_items(self, name: tuple[int, ...] = ()) -> list[Item]:
        """Return the items starting with `name`, sorted by name.

        An empty `name` returns all of the items.
        """
        return [
            self.items[item_name]
            for item_name in sorted(self.items)
            if item_name[: len(name)] == name
        ]

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
        item: Item = Item(name, title, created=stamp, updated=stamp, tag=tag)
        try:
            item_directory.mkdir()
            write_item(
                item_directory, {**new_metadata(item.state, stamp), "tag": tag}
            )
            write_file(
                item_directory / "Context.md", "# LLM Agent Context Log\n"
            )
            write_file(
                item_directory / "Details.md", f"# {number} {title}\n"
            )
            write_summary_heading(
                item_directory, summary_heading(f"{self.prefix}{tag}", title)
            )
        except OSError as error:
            return (
                f"Unable to create item directory '{item_directory}': {error}"
            )
        self.items[name] = item
        self.directories[name] = item_directory
        return item

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
            write_summary_heading(
                old_directory, summary_heading(f"{self.prefix}{tag}", title)
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

    def plan_place(
        self,
        moving: list[tuple[int, ...]],
        place: str,
        target: tuple[int, ...],
    ) -> tuple[dict[tuple[int, ...], tuple[int, ...]], tuple[int, ...]] | str:
        """Plan putting the `moving` siblings (or a new item) at a place.

        `place` is "" for the free number `target`, or "before" or "after"
        the existing item `target`.  `moving` is empty for a new item.  The
        names refer to the items before anything moves.  Returns the new
        name of every item whose name changes, and the new name of the
        first moved (or new) item, or an error string if the place is not
        valid.
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
        siblings[index:index] = moving or [NEW_ITEM]
        children[NEW_ITEM] = []
        new_names: dict[tuple[int, ...], tuple[int, ...]] = {}

        def number(
            parent: tuple[int, ...], new_parent: tuple[int, ...]
        ) -> None:
            for position, name in enumerate(children[parent], 1):
                new_names[name] = new_parent + (position,)
                number(name, new_names[name])

        number((), ())
        first: tuple[int, ...] = new_names[(moving or [NEW_ITEM])[0]]
        return {
            old: new
            for old, new in new_names.items()
            if old != new and old != NEW_ITEM
        }, first

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

    def set_state(
        self, name: tuple[int, ...], state: str, recursive: bool = False
    ) -> list[Item] | str:
        """Set the state of item `name`, and its children if `recursive`.

        An item already in `state` is left unchanged.  Otherwise its
        updated time is set to now and the change is added to its history.
        Returns the selected items, or an error string on failure.
        """
        if state not in STATES:
            return f"State '{state}' is not one of {', '.join(STATES)}"
        changed: list[Item] | str = self.select_items(name, recursive)
        if isinstance(changed, str):
            return changed
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

    def feature_command(self, command: str, arguments: list[str]) -> str:
        """Run `enable FEATURE` or `disable FEATURE`.

        FEATURE may be any unique prefix of a feature.  Returns an empty
        string on success, or an error string on failure.
        """
        found: list[str] = matches(arguments[0], FEATURES) if arguments else []
        if len(arguments) != 1 or len(found) != 1:
            return (
                f"Usage: tracker COLLECTION {command} FEATURE, where "
                f"FEATURE is one of: {', '.join(FEATURES)}"
            )
        return self.set_feature(found[0], command == "enable")

    def priority_command(self, arguments: list[str]) -> str:
        """Run `priority NUMBER LEVEL`.

        Returns an empty string on success, or an error string on failure.
        """
        if not self.priority_enabled:
            name: str = self.items_directory.name
            return (
                f"Priority is not enabled for '{name}'; use "
                f"`tracker {name} enable priority`"
            )
        if len(arguments) != 2:
            return "Usage: tracker COLLECTION priority NUMBER LEVEL"
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

    def create_command(self, arguments: list[str]) -> str:
        """Run `create [before|after] NUMBER TITLE...`.

        Returns an empty string on success, or an error string on failure.
        """
        place: str = ""
        if arguments and arguments[0] in PLACES:
            place, arguments = arguments[0], arguments[1:]
        if len(arguments) < 2:
            return (
                "Usage: tracker COLLECTION create [before|after] NUMBER "
                "TITLE..."
            )
        result: Item | str = self.create_item(
            arguments[0], " ".join(arguments[1:]), place
        )
        return result if isinstance(result, str) else ""

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
                "Usage: tracker COLLECTION move NUMBER [before|after] NUMBER"
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

    def show_command(self, arguments: list[str]) -> str:
        """Run `show NUMBER`: print an item's details and its `Details.md`.

        Returns an empty string on success, or an error string on failure.
        """
        if len(arguments) != 1:
            return "Usage: tracker COLLECTION show NUMBER"
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
                "Priority:  "
                f"{'-' if item.priority is None else item.priority}"
            )
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
        print("\n".join(lines) + "\n")
        print(details, end="")
        return ""

    def show_renumbered(self, renumbered: dict[str, Item]) -> None:
        """Print the `renumbered` items, keyed by their old numbers."""
        if renumbered:
            print("Renumbered (old number first):")
            self.show(
                list(renumbered.values()), old_numbers=list(renumbered)
            )

    def list_command(self, arguments: list[str]) -> str:
        """Run `list [-a] [-l] [NUMBER]`.

        Closed items are left out, unless `-a` is given or it is the item
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
            return "Usage: tracker COLLECTION list [-a] [-l] [NUMBER]"
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
                if item.state != "Closed" or item.name == name
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
                f"({hidden} Closed item{'' if hidden == 1 else 's'} not "
                "shown; `ls -a` shows them)"
            )
        return ""

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
        state: str = {
            "pending": "Pending",
            "open": "Open",
            "reference": "Reference",
            "suspend": "Suspended",
            "close": "Closed",
        }[command]
        changed: list[Item] | str = self.set_state(name, state, recursive)
        if isinstance(changed, str):
            return changed
        self.show(changed)
        return ""

    def rename_command(
        self, arguments: list[str], ask: Callable[[str], str] = input
    ) -> str:
        """Run `rename NUMBER to TITLE...`.

        A rename of an existing item to a usable title may first ask to
        continue (see `confirm_snapshot()`).  Returns an empty string on
        success, or an error string on failure.
        """
        if len(arguments) < 3 or arguments[1] != "to":
            return "Usage: tracker COLLECTION rename NUMBER to TITLE..."
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
        return self.update_references(old_tag, new_tag, ask)

    def update_references(
        self, old_tag: str, new_tag: str, ask: Callable[[str], str]
    ) -> str:
        """Offer to change `old_tag` to `new_tag` in the project's `.md` files.

        The files are found by `tag_references()` in the directory that
        holds the collections, and are only changed if `ask` gets a yes.
        Returns an empty string on success, or an error string on failure.
        """
        root: Path = self.items_directory.parent
        paths: list[Path] = tag_references(root, old_tag)
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
            print(f"Not updated; {old_tag} is still used in them")
            return ""
        pattern: re.Pattern[str] = tag_pattern(old_tag)
        for path in paths:
            try:
                write_file(path, pattern.sub(new_tag, read_file(path)))
            except OSError as error:
                return f"Unable to update '{path}': {error}"
        print(f"Updated {old_tag} to {new_tag} in {len(paths)} files")
        return ""

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
            return "Usage: tracker COLLECTION delete [-r] NUMBER"
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
            answer: str = ask(f"Create tracker directory '{path}'? [y/N] ")
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

    @staticmethod
    def run_command(
        arguments: list[str], ask: Callable[[str], str] = input
    ) -> int:
        """Run an item tracker command.

        `ask` is called with a yes/no question before a new collection is
        created, and returns the answer.  Returns 0 for success and 1 for
        failure.
        """
        if not arguments or arguments[0] in ("-h", "--help"):
            print(HELP)
            return 0
        if arguments == ["--test"]:  # pragma: no cover
            # The tests are in `tracker_test.py`, next to this file (even
            # when tracker is run through a symbolic link).  They are not
            # run from here when coverage is measured, which runs
            # `tracker_test.py` itself.
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import tracker_test

            return tracker_test.test()
        error: str = ""
        directories: list[Path] = find_collections(Path.cwd())
        names: list[str] = [directory.name for directory in directories]
        found: list[str] = matches(arguments[0], names)
        tag: str = ""
        if not found and tag_collection(arguments[0], names):
            found = [tag_collection(arguments[0], names)]
            tag = arguments[0]
        commands: list[str] = (
            sorted(
                {COMMANDS[name] for name in matches(arguments[1], COMMANDS)}
            )
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
            error = "Usage: tracker COLLECTION COMMAND [ARGUMENTS...]"
        elif not commands:
            error = (
                f"Unknown command '{arguments[1]}'; the commands are: "
                f"{', '.join(COMMANDS)}"
            )
        elif len(commands) > 1:
            error = (
                f"'{arguments[1]}' matches more than one command: "
                f"{', '.join(commands)}"
            )
        elif tag and commands[0] not in TAG_COMMANDS:
            error = f"A tag can not be used with '{commands[0]}'"
        elif not found and commands == ["create"] and len(arguments) == 2:
            return Items.create_collection(arguments[0], directories, ask)
        elif not found:
            error = f"No collection matches '{arguments[0]}'"
            if names:
                error += f"; the collections are: {', '.join(names)}"
            error += "\nUse `tracker NAME create` to create one."
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
        match commands[0]:
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
            case "show":
                error = items.show_command(rest)
            case "enable" | "disable":
                error = items.feature_command(commands[0], rest)
            case state_command:
                error = items.state_command(state_command, rest)
        if not error:
            error = write_startup(
                [
                    collection
                    for collection in collections
                    if not collection.error
                ]
            )
        if error:
            print(error, file=sys.stderr)
            return 1
        return 0


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
        for item in collection.list_items():
            item_directory: Path = collection.directories[item.name]
            relative: str = Path(
                os.path.relpath(item_directory, startup.items_directory)
            ).as_posix()
            if item.state == "Closed":
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
            if item.state in CONTEXT_STATES:
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


def closed_time(item: "Item", item_directory: Path) -> str:
    """Return when `item` was last Closed, from its state history.

    Returns its updated time if the history does not say.
    """
    with contextlib.suppress(OSError, ValueError):
        history: object = read_item(item_directory).get("history")
        for change in reversed(history if isinstance(history, list) else []):
            if isinstance(change, dict) and change.get("state") == "Closed":
                return str(change.get("time", item.updated))
    return item.updated


def write_closed(closed_path: Path, older: list[tuple[str, str]]) -> str:
    """Write `Closed.md`, or remove it if there are no `older` items.

    `older` holds the tag and title of each Closed item whose summary is
    not in `Startup.md`, newest first.  Returns an empty string on
    success, or an error string on failure.
    """
    lines: list[str] = [
        "# Older Closed Items",
        "",
        "<!-- Written by tracker; do not edit. -->",
        "",
        "These closed items are only listed by tag and title; `tracker TAG",
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
        item.name: f"{prefix}{item.tag}" if item.tag else ""
        for item in items
    }
    tag_width: int = max((len(tag) for tag in tags.values()), default=0)
    state_width: int = max(len(state) for state in STATES)
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
            (
                f"{old_numbers[index]:<{old_width}} -> "
                if old_numbers
                else ""
            )
            + f"{item.number:<{width}}  "
            f"{item.state:<{state_width}}  "
            f"{levels}{tags[item.name]:<{tag_width}}  {times}{item.title}"
        )


def main() -> None:  # pragma: no cover
    """Run the item tracker."""
    sys.exit(Items.run_command(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover
    main()
