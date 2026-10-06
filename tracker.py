#!/usr/bin/env python3
"""A general purpose command line tool for tracking items."""

import contextlib
import io
import json
import os
import shutil
import string
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

HELP: str = """Usage: tracker COLLECTION COMMAND [ARGUMENTS...]
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
  create NUMBER TITLE...  Create an item (NUMBER is like 1.2.3)
  rename NUMBER TITLE...  Change the title of an item
  delete [-r] NUMBER      Delete an item and all of its files
  list [-l] [NUMBER]      List all items, or NUMBER and its children
  ls [-l] [NUMBER]        Same as list
  pending [-r] NUMBER     Set the item state to Pending
  open [-r] NUMBER        Set the item state to Open
  reference [-r] NUMBER   Set the item state to Reference
  suspend [-r] NUMBER     Set the item state to Suspended
  close [-r] NUMBER       Set the item state to Closed
  help                    Print this help message

Options:
  -r, --recursive         Also apply to all of the child items
  -l, --long              Also list the created and updated times

Item states are: Pending, Open, Reference, Suspended, Closed
New items are created Pending.  Open items are being worked on.  Reference
items are not, but like Open items their Context.md is in Startup.md."""

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

# The collection that holds `Startup.md` for all of the collections.
STARTUP_COLLECTION: str = "TASKS"

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
    "help": "help",
}

# A test check: called with a condition that should be true and a description.
Check = Callable[[bool, str], None]


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


def update_item(item_directory: Path, state: str = "") -> str:
    """Set the updated time in the `.item.json` of `item_directory` to now.

    If `state` is given, the state is changed too, and the change is
    appended to the "history" list.  Any other metadata is kept.  Returns
    the new updated time.  Raises an `OSError` or a `ValueError` like
    `read_item()`.
    """
    metadata: dict[str, object] = read_item(item_directory)
    stamp: str = utc_stamp(time.time())
    metadata["updated"] = stamp
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
    command: str, arguments: list[str]
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
    name: tuple[int, ...] | str = parse_number(numbers[0])
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
        if self.error:
            print(self.error, file=sys.stderr)
        else:
            self.load_items()

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
            try:
                self.items[name] = Item(
                    name,
                    title,
                    state,
                    str(metadata.get("created", "")),
                    str(metadata.get("updated", "")),
                )
            except ValueError as error:
                print(f"Skipping '{item_directory}': {error}", file=sys.stderr)
            else:
                self.directories[name] = item_directory

    def list_items(self, name: tuple[int, ...] = ()) -> list[Item]:
        """Return the items starting with `name`, sorted by name.

        An empty `name` returns all of the items.
        """
        return [
            self.items[item_name]
            for item_name in sorted(self.items)
            if item_name[: len(name)] == name
        ]

    def create_item(self, number: str, title: str) -> Item | str:
        """Create a new Item.

        Returns the new Item, or an error string if it can not be created.
        """
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
        title = title.strip()
        cleaned_title: str = clean_title(title)
        if not cleaned_title:
            return f"Item '{number}' has an empty title"
        item_directory: Path = (
            self.items_directory / f"{number}_{cleaned_title}"
        )
        stamp: str = utc_stamp(time.time())
        item: Item = Item(name, title, created=stamp, updated=stamp)
        try:
            item_directory.mkdir()
            write_item(item_directory, new_metadata(item.state, stamp))
            write_file(
                item_directory / "Context.md", "# LLM Agent Context Log\n"
            )
            write_file(
                item_directory / "Details.md", f"# {number} {title}\n"
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
        `Details.md` is rewritten, or added if it is missing.  The updated
        time is set to now.  Returns the renamed item, or an error string
        if it can not be renamed.
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
        details_path: Path = old_directory / "Details.md"
        try:
            details: str = read_file(details_path)
            heading, _, rest = details.partition("\n")
            if not heading.startswith(f"# {number} "):
                rest = details
            write_file(details_path, f"# {number} {title}\n{rest}")
            updated: str = update_item(old_directory)
            old_directory.rename(new_directory)
        except (OSError, ValueError) as error:
            return f"Unable to rename item '{number}': {error}"
        item: Item = self.items[name]
        item.title = title
        item.updated = updated
        self.directories[name] = new_directory
        return item

    def delete_item(
        self, name: tuple[int, ...], recursive: bool = False
    ) -> list[Item] | str:
        """Delete item `name`, and its children if `recursive`.

        Each item directory is removed along with everything in it.
        Returns the deleted items, or an error string on failure.
        """
        selected: list[Item] | str = self.select_items(name, recursive)
        if isinstance(selected, str):
            return selected
        for item in selected:
            item_directory: Path = self.directories[item.name]
            try:
                shutil.rmtree(item_directory)
            except OSError as error:
                return f"Unable to delete '{item_directory}': {error}"
            del self.items[item.name]
            del self.directories[item.name]
        return selected

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

    def create_command(self, arguments: list[str]) -> str:
        """Run `create NUMBER TITLE...`.

        Returns an empty string on success, or an error string on failure.
        """
        if len(arguments) < 2:
            return "Usage: tracker COLLECTION create NUMBER TITLE..."
        result: Item | str = self.create_item(
            arguments[0], " ".join(arguments[1:])
        )
        return result if isinstance(result, str) else ""

    def list_command(self, arguments: list[str]) -> str:
        """Run `list [-l] [NUMBER]`.

        Returns an empty string on success, or an error string on failure.
        """
        long: bool = False
        numbers: list[str] = []
        for argument in arguments:
            if argument in ("-l", "--long"):
                long = True
            else:
                numbers.append(argument)
        if len(numbers) > 1:
            return "Usage: tracker COLLECTION list [-l] [NUMBER]"
        name: tuple[int, ...] | str = (
            parse_number(numbers[0]) if numbers else ()
        )
        if isinstance(name, str):
            return name
        print_items(self.list_items(name), long)
        return ""

    def state_command(self, command: str, arguments: list[str]) -> str:
        """Run a state command, like `open`, with `[-r] NUMBER`.

        Returns an empty string on success, or an error string on failure.
        """
        parsed: tuple[tuple[int, ...], bool] | str = parse_recursive(
            command, arguments
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
        print_items(changed)
        return ""

    def rename_command(self, arguments: list[str]) -> str:
        """Run `rename NUMBER TITLE...`.

        Returns an empty string on success, or an error string on failure.
        """
        if len(arguments) < 2:
            return "Usage: tracker COLLECTION rename NUMBER TITLE..."
        name: tuple[int, ...] | str = parse_number(arguments[0])
        if isinstance(name, str):
            return name
        renamed: Item | str = self.rename_item(name, " ".join(arguments[1:]))
        if isinstance(renamed, str):
            return renamed
        print_items([renamed])
        return ""

    def delete_command(self, arguments: list[str]) -> str:
        """Run `delete [-r] NUMBER`.

        Returns an empty string on success, or an error string on failure.
        """
        parsed: tuple[tuple[int, ...], bool] | str = parse_recursive(
            "delete", arguments
        )
        if isinstance(parsed, str):
            return parsed
        deleted: list[Item] | str = self.delete_item(*parsed)
        if isinstance(deleted, str):
            return deleted
        print_items(deleted)
        return ""

    @staticmethod
    def test() -> int:
        """Test the item tracker in a temporary directory.

        Prints any failed checks and a summary.  Returns 0 if every check
        passes and 1 otherwise.
        """
        failures: list[str] = []
        checks: list[str] = []

        def check(condition: bool, description: str) -> None:
            checks.append(description)
            if not condition:  # pragma: no cover
                failures.append(description)
                print(f"FAIL: {description}", file=sys.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            root: Path = Path(temporary)
            Items._test_parsing(check)
            Items._test_items(check, root / "TASKS")
            Items._test_reload(check, root / "TASKS")
            Items._test_rename_delete(check, root / "rename_delete")
            Items._test_errors(check, root / "errors")
        # The commands search upward for collections, so they are tested
        # away from the collections made by the other tests.
        with tempfile.TemporaryDirectory() as temporary:
            Items._test_commands(check, Path(temporary) / "commands")
        print(f"{len(checks)} checks, {len(failures)} failures")
        return 1 if failures else 0

    @staticmethod
    def _test_parsing(check: Check) -> None:
        """Test `parse_number()` and `Item` validation."""
        check(parse_number("1.2.3") == (1, 2, 3), "parse 1.2.3")
        check(parse_number("01.2") == (1, 2), "parse 01.2")
        for number in ("", "0", "-1", "1..2", "1.2.", "a.b", "1.0"):
            check(
                isinstance(parse_number(number), str),
                f"reject number {number!r}",
            )
        for title, cleaned in (
            ("fix the-bug, (now)!", "Fix_the_bug_now"),
            ("`README.md` documentation", "README.md_documentation"),
            ("`.pth` files", ".pth_files"),
            ("item 1.2.3", "Item_1.2.3"),
            ("say $HOME's `ls` & <more>; ok?", "Say_HOMEs_ls_more_ok"),
            ("  ... !! ", ""),
        ):
            check(
                clean_title(title) == cleaned,
                f"clean_title({title!r})",
            )
        names: list[str] = ["TASKS", "Tools", "ISSUES"]
        for word, matched in (
            ("t", ["TASKS", "Tools"]), ("TA", ["TASKS"]), ("i", ["ISSUES"]),
            ("x", []), ("", names), ("tasks", ["TASKS"]),
        ):
            check(matches(word, names) == matched, f"matches({word!r})")
        check(
            matches("task", ["TASK", "TASKS"]) == ["TASK"],
            "an exact match wins",
        )
        check(utc_stamp(0) == "1970-01-01T00:00:00Z", "utc_stamp")
        epoch: datetime = datetime.fromtimestamp(0, UTC).astimezone()
        check(
            local_time("1970-01-01T00:00:00Z")
            == epoch.strftime("%Y-%m-%d %H:%M"),
            "local_time",
        )
        for stamp, shown in (("", "-"), ("junk", "?"), ("2026-01-01", "?")):
            check(local_time(stamp) == shown, f"local_time({stamp!r})")
        check(Item((1, 2), "p").number == "1.2", "Item.number")
        check(Item((1,), "p").state == "Pending", "default is Pending")
        for state in STATES:
            check(Item((1,), "p", state).state == state, f"{state} ok")
        bad_items: list[tuple[object, str]] = [
            ((), "Open"), ((0,), "Open"), ((True,), "Open"),
            ((1, "2"), "Open"), ([1], "Open"), ((1,), "Done"),
        ]
        for name, state in bad_items:
            try:
                Item(name, "p", state)  # type: ignore[arg-type]
            except ValueError:
                check(True, f"reject Item({name!r}, {state!r})")
            else:  # pragma: no cover
                check(False, f"reject Item({name!r}, {state!r})")

    @staticmethod
    def _test_items(check: Check, directory: Path) -> None:
        """Test creating, listing and changing the state of items."""
        items: Items = Items(directory)
        check(
            not items.error and (directory / COLLECTION_FILE).is_file(),
            "create TASKS",
        )
        item: Item | str = items.create_item("1", "  top item  ")
        check(
            isinstance(item, Item) and item.title == "top item",
            "create item 1",
        )
        top: Path = directory / "1_Top_item"
        metadata: dict[str, object] = read_item(top)
        check(
            read_file(top / ITEM_FILE).startswith(
                '{\n  "state": "Pending",\n'
            )
            and isinstance(item, Item)
            and metadata == new_metadata("Pending", item.created)
            and local_time(item.created) not in ("-", "?"),
            "item file",
        )
        check(
            read_file(top / "Context.md") == "# LLM Agent Context Log\n",
            "Context.md file",
        )
        check(
            read_file(top / "Details.md") == "# 1 top item\n",
            "Details.md file",
        )
        items.create_item("1.2", "fix the-bug, (now)!")
        check(
            (directory / "1.2_Fix_the_bug_now").is_dir(),
            "directory name is cleaned up",
        )
        # Created out of order to test that listing sorts numerically.
        for number in ("2", "1.20", "1.2.10", "1.2.3"):
            items.create_item(number, f"item {number}")
        for number, title in (
            ("1.2", "duplicate"), ("01.2", "duplicate"),
            ("x", "bad"), ("3", "  ...!! "), ("4", ""),
        ):
            check(
                isinstance(items.create_item(number, title), str),
                f"reject create {number!r} {title!r}",
            )
        check(
            not any(directory.glob("3_*")) and not any(directory.glob("4_*")),
            "rejected items have no directory",
        )
        items.set_state((1,), "Open", True)
        items.set_state((2,), "Open")
        Items._test_list_and_state(check, items, directory)

    @staticmethod
    def _test_list_and_state(
        check: Check, items: "Items", directory: Path
    ) -> None:
        """Test `list_items()`, `set_state()` and `write_startup()`."""

        def numbers(listed: list[Item] | str) -> list[str]:
            if isinstance(listed, str):  # pragma: no cover
                return [listed]
            return [item.number for item in listed]

        check(
            numbers(items.list_items())
            == ["1", "1.2", "1.2.3", "1.2.10", "1.20", "2"],
            "list all items in numeric order",
        )
        check(
            numbers(items.list_items((1, 2)))
            == ["1.2", "1.2.3", "1.2.10"],
            "list 1.2 and its children",
        )
        check(items.list_items((9,)) == [], "list with no matches")
        check(
            numbers(items.set_state((1, 2), "Closed")) == ["1.2"],
            "close 1.2",
        )
        check(
            read_item(directory / "1.2_Fix_the_bug_now")["state"]
            == "Closed",
            "close 1.2 writes item file",
        )
        history: object = read_item(directory / "1.2_Fix_the_bug_now")[
            "history"
        ]
        check(
            isinstance(history, list)
            and [change["state"] for change in history]
            == ["Pending", "Open", "Closed"],
            "history of 1.2",
        )
        check(items.items[(1, 2, 3)].state == "Open", "1.2.3 still Open")
        check(
            numbers(items.set_state((1, 2), "Suspended", True))
            == ["1.2", "1.2.3", "1.2.10"],
            "suspend -r 1.2",
        )
        check(items.items[(1, 20)].state == "Open", "1.20 still Open")
        for name, state, recursive in (
            ((9,), "Closed", False), ((9,), "Closed", True),
            ((1,), "Done", False),
        ):
            check(
                isinstance(items.set_state(name, state, recursive), str),
                f"reject set_state {name} {state} {recursive}",
            )
        items.set_state((2,), "Reference")
        items.create_item("3", "Later")
        issues: Items = Items(directory.parent / "ISSUES")
        issues.create_item("1", "Crash")
        issues.set_state((1,), "Open")
        check(write_startup([issues]) == "", "no TASKS, no Startup.md")
        check(
            not (issues.items_directory / "Startup.md").exists(),
            "Startup.md is only written into TASKS",
        )
        check(write_startup([issues, items]) == "", "write Startup.md")
        check(
            read_file(directory / "Startup.md")
            == "@1_Top_item/Details.md\n@1_Top_item/Context.md\n"
            "@1.2_Fix_the_bug_now/Details.md\n"
            "@1.2.3_Item_1.2.3/Details.md\n"
            "@1.2.10_Item_1.2.10/Details.md\n"
            "@1.20_Item_1.20/Details.md\n@1.20_Item_1.20/Context.md\n"
            "@2_Item_2/Details.md\n@2_Item_2/Context.md\n"
            "@3_Later/Details.md\n"
            "@../ISSUES/1_Crash/Details.md\n"
            "@../ISSUES/1_Crash/Context.md\n",
            "Startup.md contents",
        )

    @staticmethod
    def _test_reload(check: Check, directory: Path) -> None:
        """Test loading items back from disk, including bad directories."""
        (directory / "junk").mkdir()
        bad_state: Path = directory / "5_Bad_state"
        bad_state.mkdir()
        write_item(bad_state, {"state": "Done"})
        write_file(bad_state / "Details.md", "# 5 Bad state\n")
        for directory_name, text in (
            ("6_Bad_json", "{"), ("7_Not_object", "[]")
        ):
            (directory / directory_name).mkdir()
            write_file(directory / directory_name / ITEM_FILE, text)
            write_file(directory / directory_name / "Details.md", "# x\n")
        old_format: Path = directory / "8_Old_format"
        old_format.mkdir()
        write_file(old_format / OLD_STATUS_FILE, "Suspended\n")
        os.utime(old_format / OLD_STATUS_FILE, (0, 0))
        write_file(old_format / "Details.md", "# 8 Old format\n")
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            items: Items = Items(directory)
        check(errors.getvalue().count("Skipping") == 4, "skip bad items")
        check(len(items.items) == 8, "reload 8 items")
        check(
            items.items[(8,)].state == "Suspended"
            and not (old_format / OLD_STATUS_FILE).exists()
            and items.items[(8,)].created == "1970-01-01T00:00:00Z"
            and read_item(old_format)
            == new_metadata("Suspended", "1970-01-01T00:00:00Z"),
            "migrate a .status file to .item.json",
        )
        write_item(
            old_format, {"state": "Suspended", "tags": ["x"], "updated": "x"}
        )
        items.set_state((8,), "Closed")
        metadata: dict[str, object] = read_item(old_format)
        check(
            metadata["state"] == "Closed" and metadata["tags"] == ["x"],
            "set_state keeps other item metadata",
        )
        check(
            metadata["updated"] == items.items[(8,)].updated != "x",
            "set_state sets the updated time",
        )
        items.set_state((8,), "Closed")
        check(
            read_item(old_format) == metadata,
            "set_state to the same state changes nothing",
        )
        write_file(old_format / ITEM_FILE, "[]")
        check(
            "Unable to write" in str(items.set_state((8,), "Open")),
            "set_state with a bad item file",
        )
        check(
            items.items[(1, 2)].title == "fix the-bug, (now)!",
            "reload title from Details.md",
        )
        check(
            [item.state for item in items.list_items((1,))]
            == ["Open", "Suspended", "Suspended", "Suspended", "Open"],
            "reload states",
        )
        not_a_directory: Path = directory.parent / "not_a_directory"
        write_file(not_a_directory, "")
        with contextlib.redirect_stderr(io.StringIO()):
            check(bool(Items(not_a_directory).error), "TASKS is a file")

    @staticmethod
    def _test_rename_delete(check: Check, directory: Path) -> None:
        """Test `rename_item()` and `delete_item()`."""
        items: Items = Items(directory)
        for number, title in (
            ("1", "One"), ("1.1", "Child"), ("2", "Two")
        ):
            items.create_item(number, title)
        write_item(directory / "1_One", {"state": "Open", "updated": "x"})
        renamed: Item | str = items.rename_item((1,), " Uno, again ")
        check(
            isinstance(renamed, Item) and renamed.title == "Uno, again",
            "rename 1",
        )
        check(
            (directory / "1_Uno_again").is_dir()
            and not (directory / "1_One").exists(),
            "rename moves the item directory",
        )
        check(
            read_file(directory / "1_Uno_again" / "Details.md")
            == "# 1 Uno, again\n",
            "rename rewrites the Details.md heading",
        )
        check(
            isinstance(renamed, Item)
            and read_item(directory / "1_Uno_again")["updated"]
            == renamed.updated
            != "x",
            "rename sets the updated time",
        )
        write_file(directory / "2_Two" / "Details.md", "Notes\n")
        items.rename_item((2,), "Two")
        check(
            read_file(directory / "2_Two" / "Details.md")
            == "# 2 Two\nNotes\n",
            "rename adds a missing Details.md heading",
        )
        (directory / "2_Taken").mkdir()
        for name, title in (((9,), "Nine"), ((1,), " !! "), ((2,), "taken")):
            check(
                isinstance(items.rename_item(name, title), str),
                f"reject rename {name} {title!r}",
            )
        (directory / "2_Taken").rmdir()
        check(
            Items(directory).items[(1,)].title == "Uno, again",
            "reload a renamed item",
        )
        deleted: list[Item] | str = items.delete_item((1,))
        check(
            not isinstance(deleted, str)
            and [item.number for item in deleted] == ["1"]
            and not (directory / "1_Uno_again").exists()
            and (directory / "1.1_Child").is_dir(),
            "delete 1 keeps 1.1",
        )
        items.create_item("1", "One")
        deleted = items.delete_item((1,), True)
        check(
            not isinstance(deleted, str)
            and [item.number for item in deleted] == ["1", "1.1"]
            and not any(directory.glob("1*")),
            "delete -r 1",
        )
        for recursive in (False, True):
            check(
                isinstance(items.delete_item((9,), recursive), str),
                f"reject delete 9 recursive={recursive}",
            )
        details_path: Path = directory / "2_Two" / "Details.md"
        details_path.unlink()
        details_path.mkdir()
        check(
            "Unable to rename" in str(items.rename_item((2,), "Deux")),
            "rename failure",
        )
        if os.geteuid() == 0:
            # Permissions are not enforced for root.
            return  # pragma: no cover
        directory.chmod(0o500)
        try:
            check(
                "Unable to delete" in str(items.delete_item((2,))),
                "delete failure",
            )
        finally:
            directory.chmod(0o700)

    @staticmethod
    def _test_commands(check: Check, directory: Path) -> None:
        """Test `run_command()` from inside `directory`."""
        answers: list[str] = []
        questions: list[str] = []

        def ask(question: str) -> str:
            questions.append(question)
            if not answers:
                raise EOFError
            return answers.pop(0)

        def run(*arguments: str) -> tuple[int, str]:
            output: io.StringIO = io.StringIO()
            with (
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(output),
            ):
                code: int = Items.run_command(list(arguments), ask)
            return code, output.getvalue()

        directory.mkdir()
        (directory / "plain").mkdir()
        original: Path = Path.cwd()
        os.chdir(directory)
        try:
            for answer, arguments, code, text in (
                ("", (), 0, "Usage"),
                ("", ("--help",), 0, "Usage"),
                ("", ("-h",), 0, "Usage"),
                ("", ("--bogus",), 1, "Unknown option"),
                ("", ("t", "ls"), 1, "No collection matches 't'\nUse"),
                ("", ("TASKS", "create"), 1, "Not created"),
                ("n", ("TASKS", "create"), 1, "Not created"),
                ("y", ("TASKS", "create"), 0, "Created"),
                ("", ("TASKS", "create"), 1, "Usage"),
                ("yes", ("Issues", "cr"), 0, "Created"),
                ("", ("a/b", "create"), 1, "Invalid collection name"),
                ("", ("..", "create"), 1, "Invalid collection name"),
                ("", ("plain", "create"), 1, "already exists"),
                ("", ("x", "ls"), 1, "the collections are: Issues, TASKS"),
                ("", ("t",), 1, "Usage"),
                ("", ("t", "h"), 0, "Usage"),
                ("", ("t", "bogus"), 1, "Unknown command"),
                ("", ("t", "c", "1"), 1, "close, create"),
                ("", ("t", "re", "1"), 1, "reference, rename"),
                ("", ("t", "l", "1"), 0, ""),
                ("", ("t", "create", "1", "An", "item"), 0, ""),
                ("", ("T", "cr", "1.1", "Child"), 0, ""),
                ("", ("tasks", "create", "1"), 1, "Usage"),
                ("", ("t", "create", "1", "again"), 1, "already exists"),
                ("", ("t", "ls"), 0, "An item"),
                ("", ("t", "list", "1.1"), 0, "Child"),
                ("", ("t", "l", "x"), 1, "Invalid"),
                ("", ("t", "ls", "1", "2"), 1, "Usage"),
                ("", ("t", "ls", "-l"), 0, "An item"),
                ("", ("t", "li", "--long", "1.1"), 0, "Child"),
                ("", ("t", "ls", "-l", "1", "2"), 1, "Usage"),
                ("", ("t", "cl", "1"), 0, "Closed"),
                ("", ("t", "s", "--recursive", "1"), 0, "1.1"),
                ("", ("t", "o", "-r", "1"), 0, "Open"),
                ("", ("t", "p", "1.1"), 0, "Pending"),
                ("", ("t", "ref", "1.1"), 0, "Reference"),
                ("", ("t", "open"), 1, "Usage"),
                ("", ("t", "close", "9"), 1, "does not exist"),
                ("", ("t", "close", "x"), 1, "Invalid"),
                ("", ("t", "ren", "1.1", "New", "child"), 0, "New child"),
                ("", ("t", "rename", "1"), 1, "Usage"),
                ("", ("t", "rename", "x", "y"), 1, "Invalid"),
                ("", ("t", "rename", "9", "Nine"), 1, "does not exist"),
                ("", ("t", "create", "2", "Doomed"), 0, ""),
                ("", ("t", "d", "2"), 0, "Doomed"),
                ("", ("t", "delete"), 1, "Usage"),
                ("", ("t", "delete", "x"), 1, "Invalid"),
                ("", ("t", "delete", "-r", "9"), 1, "No items match"),
                ("", ("i", "create", "1", "Crash"), 0, ""),
                ("", ("I", "OPEN", "1"), 0, "Open"),
            ):
                answers[:] = [answer] if answer else []
                result: tuple[int, str] = run(*arguments)
                check(
                    result[0] == code and text in result[1],
                    f"command {' '.join(arguments)!r}",
                )
            check(
                (directory / "TASKS" / COLLECTION_FILE).is_file()
                and (directory / "Issues" / COLLECTION_FILE).is_file()
                and not (directory / "plain" / COLLECTION_FILE).exists(),
                "create collections named as typed",
            )
            check(
                questions[0]
                == f"Create tracker directory '{Path.cwd() / 'TASKS'}'? "
                "[y/N] ",
                "ask before creating a collection",
            )
            check(
                read_file(Path("TASKS/Startup.md"))
                == "@1_An_item/Details.md\n@1_An_item/Context.md\n"
                "@1.1_New_child/Details.md\n@1.1_New_child/Context.md\n"
                "@../Issues/1_Crash/Details.md\n"
                "@../Issues/1_Crash/Context.md\n",
                "commands write Startup.md for every collection",
            )
            os.chdir(directory / "TASKS" / "1_An_item")
            check(run("t", "ls")[1].startswith("1  "), "search upward")
            answers[:] = ["y"]
            check(
                run("Tools", "create")[0] == 0
                and (directory / "Tools" / COLLECTION_FILE).is_file(),
                "create a collection next to the others",
            )
            code, text = run("t", "ls")
            check(
                code == 1 and "more than one collection: TASKS, Tools" in text,
                "ambiguous collection",
            )
            check(run("ta", "ls")[0] == 0, "unambiguous collection")
            startup: Path = directory / "TASKS" / "Startup.md"
            saved: str = read_file(startup)
            startup.unlink()
            startup.mkdir()
            answers[:] = ["y"]
            code, text = run("Docs", "create")
            check(
                code == 1 and "Unable to write" in text,
                "create a collection when Startup.md can not be written",
            )
            startup.rmdir()
            write_file(startup, saved)
            if os.geteuid() == 0:
                # Permissions are not enforced for root.
                return  # pragma: no cover
            (directory / "Tools").chmod(0o500)
            try:
                code, text = run("to", "ls")
                check(
                    code == 1 and "No write access" in text,
                    "command in a read-only collection",
                )
            finally:
                (directory / "Tools").chmod(0o700)
            (directory / "TASKS").chmod(0o500)
            answers[:] = ["y"]
            try:
                code, text = run("Rules", "create")
                check(
                    code == 0
                    and "No write access" in text
                    and "@1_An_item/" in read_file(
                        directory / "TASKS" / "Startup.md"
                    ),
                    "create a collection with a read-only TASKS",
                )
            finally:
                (directory / "TASKS").chmod(0o700)
            (directory).chmod(0o500)
            answers[:] = ["y"]
            try:
                code, text = run("More", "create")
                check(
                    code == 1 and "Unable to create" in text,
                    "create a collection in a read-only directory",
                )
            finally:
                directory.chmod(0o700)
        finally:
            os.chdir(original)

    @staticmethod
    def _test_errors(check: Check, directory: Path) -> None:
        """Test the error paths for files that can not be read or written."""
        directory.mkdir()
        items: Items = Items(directory / "TASKS")
        items.create_item("1", "One")
        no_state: Path = directory / "TASKS" / "2_No_state"
        no_state.mkdir()
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            items = Items(directory / "TASKS")
        check("2_No_state" in errors.getvalue(), "skip missing state file")
        state_path: Path = directory / "TASKS" / "1_One" / ITEM_FILE
        state_path.unlink()
        state_path.mkdir()
        check(
            "Unable to write" in str(items.set_state((1,), "Closed")),
            "set_state write failure",
        )
        (directory / "TASKS" / "Startup.md").mkdir()
        check(
            "Unable to write" in write_startup([items]),
            "write_startup failure",
        )
        if os.geteuid() == 0:
            # Permissions are not enforced for root.
            return  # pragma: no cover
        read_only: Path = directory / "read_only"
        read_only.mkdir(mode=0o500)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                items = Items(read_only)
            check("No write access" in items.error, "read-only TASKS")
            check(
                "Unable to create" in str(items.create_item("1", "One")),
                "create_item in read-only TASKS",
            )
        finally:
            read_only.chmod(0o700)

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
        if arguments == ["--test"]:
            return Items.test()
        error: str = ""
        directories: list[Path] = find_collections(Path.cwd())
        names: list[str] = [directory.name for directory in directories]
        found: list[str] = matches(arguments[0], names)
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
        rest: list[str] = arguments[2:]
        match commands[0]:
            case "help":
                print(HELP)
            case "create":
                error = items.create_command(rest)
            case "list":
                error = items.list_command(rest)
            case "rename":
                error = items.rename_command(rest)
            case "delete":
                error = items.delete_command(rest)
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
    """Write `Startup.md` into the TASKS collection, if there is one.

    Every line is an `@` import, relative to the TASKS collection, of the
    `Details.md` of every item, and the `Context.md` of every Open or
    Reference item, so that adding `@TASKS/Startup.md` to `CLAUDE.md`
    loads them.  The TASKS items come first, then the items of the other
    `collections` in order.  Returns an empty string on success, or an
    error string on failure.
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
    for collection in [startup] + [
        collection for collection in collections if collection is not startup
    ]:
        for item in collection.list_items():
            item_directory: Path = collection.directories[item.name]
            relative: str = Path(
                os.path.relpath(item_directory, startup.items_directory)
            ).as_posix()
            file_names: tuple[str, ...] = ("Details.md",)
            if item.state in CONTEXT_STATES:
                file_names += ("Context.md",)
            for file_name in file_names:
                if (item_directory / file_name).is_file():
                    lines.append(f"@{relative}/{file_name}")
    startup_path: Path = startup.items_directory / "Startup.md"
    try:
        write_file(startup_path, "".join(f"{line}\n" for line in lines))
    except OSError as error:
        return f"Unable to write '{startup_path}': {error}"
    return ""


def print_items(items: list[Item], long: bool = False) -> None:
    """Print one line per item with its number, state and title.

    If `long`, the created and updated times are also printed in the
    local time zone.
    """
    width: int = max((len(item.number) for item in items), default=0)
    state_width: int = max(len(state) for state in STATES)
    time_width: int = len("YYYY-MM-DD HH:MM")
    for item in items:
        times: str = (
            f"{local_time(item.created):<{time_width}}  "
            f"{local_time(item.updated):<{time_width}}  "
            if long
            else ""
        )
        print(
            f"{item.number:<{width}}  "
            f"{item.state:<{state_width}}  {times}{item.title}"
        )


def main() -> None:
    """Run the item tracker."""
    sys.exit(Items.run_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
