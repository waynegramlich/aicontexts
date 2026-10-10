"""The tests of ai_contexts, run by `ai_contexts --test`."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

from ai_contexts import (
    CLOSED_SUMMARIES,
    COLLECTION_FILE,
    DELAY_VARIABLE,
    FORMAT_VERSION,
    INTERRUPT_VARIABLE,
    ITEM_FILE,
    OLD_COLLECTION_FILE,
    OLD_STATUS_FILE,
    RENUMBER_FILE,
    RULES_FILE,
    RULES_TEXT,
    STATES,
    SUMMARIES_VARIABLE,
    Item,
    Items,
    RenumberInterrupted,
    base_tag,
    clean_title,
    closed_time,
    find_collections,
    has_summary,
    local_time,
    matches,
    new_metadata,
    parse_number,
    parse_priority,
    print_items,
    read_file,
    read_item,
    sha256_of,
    tag_prefix,
    tag_references,
    unique_tag,
    utc_stamp,
    write_file,
    write_item,
    write_startup,
)

# A test check: called with a condition that should be true and a
# description.
Check: TypeAlias = Callable[[bool, str], None]


# Function `test()`:
def test() -> int:
    """Test ai_contexts in a temporary directory.

    Prints any failed checks and a summary.

    Returns:
    * (`int`): 0 if every check passes and 1 otherwise.
    """
    failures: list[str] = []
    checks: list[str] = []

    def check(condition: bool, description: str) -> None:
        """Record a check, and print it if it failed.

        Arguments:
        * `condition` (`bool`):
          The condition, which should be true.
        * `description` (`str`):
          What is checked.
        """
        checks.append(description)
        if not condition:  # pragma: no cover
            failures.append(description)
            print(f"FAIL: {description}", file=sys.stderr)

    temporary: str
    with tempfile.TemporaryDirectory() as temporary:
        root: Path = Path(temporary)
        _test_parsing(check)
        _test_items(check, root / "TASKS")
        _test_reload(check, root / "TASKS")
        _test_rename_delete(check, root / "rename_delete")
        _test_numbering(check, root / "numbering")
        _test_moving(check, root / "moving")
        _test_recovery(check, root / "recovery")
        _test_references(check, root / "references")
        _test_closed(check, root / "closed")
        _test_checks(check, root / "checks")
        _test_write_failures(check, root / "failures")
        _test_errors(check, root / "errors")
    # The commands search upward for collections, so they are tested
    # away from the collections made by the other tests.
    with tempfile.TemporaryDirectory() as temporary:
        _test_commands(check, Path(temporary) / "commands")
    with tempfile.TemporaryDirectory() as temporary:
        _test_types(check, Path(temporary))
    with tempfile.TemporaryDirectory() as temporary:
        _test_rules(check, Path(temporary))
    with tempfile.TemporaryDirectory() as temporary:
        _test_transfer(check, Path(temporary))
    with tempfile.TemporaryDirectory() as temporary:
        _test_transfer_recovery(check, Path(temporary))
    with tempfile.TemporaryDirectory() as temporary:
        _test_old_collection_file(check, Path(temporary))
    with tempfile.TemporaryDirectory() as temporary:
        _test_rules_files(check, Path(temporary))
    with tempfile.TemporaryDirectory() as temporary:
        _test_version_control_root(check, Path(temporary))
    print(f"{len(checks)} checks, {len(failures)} failures")
    return 1 if failures else 0


# Function `_test_parsing()`:
def _test_parsing(check: Check) -> None:
    """Test `parse_number()` and `Item` validation.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    """
    check(parse_number("1.2.3") == (1, 2, 3), "parse 1.2.3")
    check(parse_number("01.2") == (1, 2), "parse 01.2")
    number: str
    for number in ("", "0", "-1", "1..2", "1.2.", "a.b", "1.0"):
        check(
            isinstance(parse_number(number), str),
            f"reject number {number!r}",
        )
    title: str
    cleaned: str
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
    word: str
    matched: object
    for word, matched in (
        ("t", ["TASKS", "Tools"]),
        ("TA", ["TASKS"]),
        ("i", ["ISSUES"]),
        ("x", []),
        ("", names),
        ("tasks", ["TASKS"]),
    ):
        check(matches(word, names) == matched, f"matches({word!r})")
    check(
        matches("task", ["TASK", "TASKS"]) == ["TASK"],
        "an exact match wins",
    )
    tag: str
    for title, tag in (
        ("Division by Zero is Bad", "dbzib"),
        ("Can Dogs Eat", "cde"),
        ("the re-run of an old-test", "ro"),
        ("fix the-bug, (now)!", "ftn"),
        ("`README.md` documentation", "rd"),
        ("Item 1.2.3", "i1"),
        ("The A, of AN", "t"),
        ("!!", ""),
    ):
        check(base_tag(title) == tag, f"base_tag({title!r})")
    unique_cases: list[tuple[str, list[str], str]] = [
        ("cde", [], "cde"),
        ("cde", ["cde"], "cde2"),
        ("cde", ["cde", "cde2", "cde4"], "cde3"),
    ]
    base: str
    used: list[str]
    for base, used, tag in unique_cases:
        check(unique_tag(base, used) == tag, f"unique_tag {used}")
    level: str
    priority: int | None
    for level, priority in (("0", 0), ("3", 3), ("-", None)):
        check(parse_priority(level) == priority, f"parse_priority({level})")
    for level in ("4", "-1", "x", "", "1.0"):
        check(
            isinstance(parse_priority(level), str),
            f"reject priority {level!r}",
        )
    printed: list[Item] = [
        Item((1,), "Can Dogs Eat", tag="cde", priority=0),
        Item((1, 2), "X", "Reference", tag="x"),
    ]
    output: io.StringIO = io.StringIO()
    with contextlib.redirect_stdout(output):
        print_items(printed)
        print_items(printed, priority=True, prefix="I.")
    check(
        output.getvalue() == "1    Pending    cde  Can Dogs Eat\n"
        "1.2  Reference  x    X\n"
        "1    Pending    0  I.cde  Can Dogs Eat\n"
        "1.2  Reference  -  I.x    X\n",
        "print_items shows the tag, and the priority if asked",
    )
    collection_name: str
    prefix: str
    for collection_name, prefix in (
        ("TASKS", "T."),
        ("issues", "I."),
        ("2026", "2."),
    ):
        check(
            tag_prefix(collection_name) == prefix,
            f"tag_prefix({collection_name!r})",
        )
    check(utc_stamp(0) == "1970-01-01T00:00:00Z", "utc_stamp")
    epoch: datetime = datetime.fromtimestamp(0, UTC).astimezone()
    check(
        local_time("1970-01-01T00:00:00Z") == epoch.strftime("%Y-%m-%d %H:%M"),
        "local_time",
    )
    stamp: str
    shown: str
    for stamp, shown in (("", "-"), ("junk", "?"), ("2026-01-01", "?")):
        check(local_time(stamp) == shown, f"local_time({stamp!r})")
    check(Item((1, 2), "p").number == "1.2", "Item.number")
    check(Item((1,), "p").state == "Pending", "default is Pending")
    state: str
    for state in STATES:
        check(Item((1,), "p", state).state == state, f"{state} ok")
    bad_items: list[tuple[object, str]] = [
        ((), "Open"),
        ((0,), "Open"),
        ((True,), "Open"),
        ((1, "2"), "Open"),
        ([1], "Open"),
        ((1,), "Done"),
    ]
    name: object
    for name, state in bad_items:
        try:
            Item(name, "p", state)  # type: ignore[arg-type]
        except ValueError:
            check(True, f"reject Item({name!r}, {state!r})")
        else:  # pragma: no cover
            check(False, f"reject Item({name!r}, {state!r})")


# Function `_test_items()`:
def _test_items(check: Check, directory: Path) -> None:
    """Test creating, listing and changing the state of items.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    items: Items = Items(directory)
    check(
        not items.error
        and read_file(directory / COLLECTION_FILE)
        == f'{{\n  "version": "{FORMAT_VERSION}"\n}}\n',
        "create TASKS with a format version",
    )
    write_file(directory / COLLECTION_FILE, '{"priority": false}\n')
    check(
        Items(directory).settings
        == {"version": FORMAT_VERSION, "priority": False}
        and json.loads(read_file(directory / COLLECTION_FILE))["version"]
        == FORMAT_VERSION,
        "add the format version to an older collection",
    )
    write_file(directory / COLLECTION_FILE, '{"version": "9.9"}\n')
    errors: io.StringIO = io.StringIO()
    with contextlib.redirect_stderr(errors):
        Items(directory)
    check(
        "has version '9.9', but this ai_contexts uses version"
        in errors.getvalue(),
        "report another format version",
    )
    write_file(directory / COLLECTION_FILE, '{"version": "0.1"}\n')
    item: Item | str = items.create_item("1", "  top item  ")
    check(
        isinstance(item, Item) and item.title == "top item",
        "create item 1",
    )
    top: Path = directory / "1_Top_item"
    metadata: dict[str, object] = read_item(top)
    check(
        read_file(top / ITEM_FILE).startswith('{\n  "state": "Pending",\n')
        and isinstance(item, Item)
        and metadata == {**new_metadata("Pending", item.created), "tag": "ti"}
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
    items.create_item("1.1", "fix the-bug, (now)!")
    check(
        (directory / "1.1_Fix_the_bug_now").is_dir(),
        "directory name is cleaned up",
    )
    number: str
    for number in ("2", "1.2", "1.1.1", "1.1.2"):
        items.create_item(number, f"item {number}")
    title: str
    for number, title in (
        ("1.1", "duplicate"),
        ("01.1", "duplicate"),
        ("x", "bad"),
        ("3", "  ...!! "),
        ("3", ""),
        ("4", "gap"),
        ("1.4", "gap"),
        ("1.1.4", "gap"),
        ("3.1", "no parent"),
    ):
        check(
            isinstance(items.create_item(number, title), str),
            f"reject create {number!r} {title!r}",
        )
    check(
        not any(directory.glob("3_*")) and not any(directory.glob("4_*")),
        "rejected items have no directory",
    )
    check(
        "the next free number is 1.3" in str(items.create_item("1.4", "x"))
        and "3 does not exist" in str(items.create_item("3.1", "x")),
        "create explains a gap",
    )
    items.set_state((1,), "Open", True)
    items.set_state((2,), "Open")
    _test_list_and_state(check, items, directory)


# Function `_test_list_and_state()`:
def _test_list_and_state(check: Check, items: Items, directory: Path) -> None:
    """Test `list_items()`, `set_state()` and `write_startup()`.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `items` (`Items`):
      The collection to test.
    * `directory` (`Path`):
      The directory to test in.
    """

    def numbers(listed: list[Item] | str) -> list[str]:
        """Return the numbers of listed items.

        Arguments:
        * `listed` (`list[Item] | str`):
          The items, or an error string.

        Returns:
        * (`list[str]`): The item numbers, or the error string alone.
        """
        if isinstance(listed, str):  # pragma: no cover
            return [listed]
        return [item.number for item in listed]

    check(
        numbers(items.list_items())
        == ["1", "1.1", "1.1.1", "1.1.2", "1.2", "2"],
        "list all items in order",
    )
    check(
        numbers(items.list_items((1, 1))) == ["1.1", "1.1.1", "1.1.2"],
        "list 1.1 and its children",
    )
    check(items.list_items((9,)) == [], "list with no matches")
    check(
        numbers(items.set_state((1, 1), "Closed")) == ["1.1"],
        "close 1.1",
    )
    check(
        read_item(directory / "1.1_Fix_the_bug_now")["state"] == "Closed",
        "close 1.1 writes item file",
    )
    history: object = read_item(directory / "1.1_Fix_the_bug_now")["history"]
    check(
        isinstance(history, list)
        and [change["state"] for change in history]
        == ["Pending", "Open", "Closed"],
        "history of 1.1",
    )
    check(items.items[(1, 1, 1)].state == "Open", "1.1.1 still Open")
    check(
        numbers(items.set_state((1, 1), "Suspended", True))
        == ["1.1", "1.1.1", "1.1.2"],
        "suspend -r 1.1",
    )
    check(items.items[(1, 2)].state == "Open", "1.2 still Open")
    name: tuple[int]
    state: str
    recursive: bool
    for name, state, recursive in (
        ((9,), "Closed", False),
        ((9,), "Closed", True),
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
        "@1.1_Fix_the_bug_now/Details.md\n"
        "@1.1.1_Item_1.1.1/Details.md\n"
        "@1.1.2_Item_1.1.2/Details.md\n"
        "@1.2_Item_1.2/Details.md\n@1.2_Item_1.2/Context.md\n"
        "@2_Item_2/Details.md\n@2_Item_2/Context.md\n"
        "@3_Later/Details.md\n"
        "@../ISSUES/1_Crash/Details.md\n"
        "@../ISSUES/1_Crash/Context.md\n",
        "Startup.md contents",
    )


# Function `_test_reload()`:
def _test_reload(check: Check, directory: Path) -> None:
    """Test loading items back from disk, including bad directories.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    (directory / "junk").mkdir()
    bad_state: Path = directory / "5_Bad_state"
    bad_state.mkdir()
    write_item(bad_state, {"state": "Done"})
    write_file(bad_state / "Details.md", "# 5 Bad state\n")
    directory_name: str
    text: str
    for directory_name, text in (("6_Bad_json", "{"), ("7_Not_object", "[]")):
        (directory / directory_name).mkdir()
        write_file(directory / directory_name / ITEM_FILE, text)
        write_file(directory / directory_name / "Details.md", "# x\n")
    old_format: Path = directory / "4_Old_format"
    old_format.mkdir()
    write_file(old_format / OLD_STATUS_FILE, "Suspended\n")
    os.utime(old_format / OLD_STATUS_FILE, (0, 0))
    write_file(old_format / "Details.md", "# 4 Old format\n")
    errors: io.StringIO = io.StringIO()
    with contextlib.redirect_stderr(errors):
        items: Items = Items(directory)
    check(errors.getvalue().count("Skipping") == 4, "skip bad items")
    check(len(items.items) == 8, "reload 8 items")
    check(
        items.items[(4,)].state == "Suspended"
        and not (old_format / OLD_STATUS_FILE).exists()
        and items.items[(4,)].created == "1970-01-01T00:00:00Z"
        and read_item(old_format)
        == {
            **new_metadata("Suspended", "1970-01-01T00:00:00Z"),
            "tag": "of",
        },
        "migrate a .status file to .item.json",
    )
    write_item(
        old_format, {"state": "Suspended", "tags": ["x"], "updated": "x"}
    )
    items.set_state((4,), "Closed")
    metadata: dict[str, object] = read_item(old_format)
    check(
        metadata["state"] == "Closed" and metadata["tags"] == ["x"],
        "set_state keeps other item metadata",
    )
    check(
        metadata["updated"] == items.items[(4,)].updated != "x",
        "set_state sets the updated time",
    )
    items.set_state((4,), "Closed")
    check(
        read_item(old_format) == metadata,
        "set_state to the same state changes nothing",
    )
    write_file(old_format / ITEM_FILE, "[]")
    check(
        "Unable to write" in str(items.set_state((4,), "Open")),
        "set_state with a bad item file",
    )
    check(
        items.items[(1, 1)].title == "fix the-bug, (now)!",
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


# Function `_test_rename_delete()`:
def _test_rename_delete(check: Check, directory: Path) -> None:
    """Test `rename_item()` and `delete_items()`.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    items: Items = Items(directory)
    number: str
    title: str
    for number, title in (("1", "One"), ("1.1", "Child"), ("2", "Two")):
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
    for number, title in (
        ("3", "Can Dogs Eat"),
        ("4", "Caffeine Drink Elixir"),
        ("5", "Hot Tub"),
    ):
        items.create_item(number, title)
    check(
        [items.items[(number,)].tag for number in (3, 4, 5)]
        == ["cde", "cde2", "ht"],
        "a clashing tag gets a number",
    )
    items.rename_item((4,), "Caffeine Drinks Everywhere")
    check(items.items[(4,)].tag == "cde2", "rename keeps an equal tag")
    items.rename_item((3,), "Hot Tea")
    check(
        items.items[(3,)].tag == "ht2"
        and read_item(directory / "3_Hot_Tea")["tag"] == "ht2",
        "rename makes a new unique tag",
    )
    check(
        [item.tag for item in Items(directory).list_items((3,))] == ["ht2"],
        "reload a tag",
    )
    items.delete_items([(3,), (4,), (5,)])
    write_file(directory / "2_Two" / "Details.md", "Notes\n")
    items.rename_item((2,), "Two")
    check(
        read_file(directory / "2_Two" / "Details.md") == "# 2 Two\nNotes\n",
        "rename adds a missing Details.md heading",
    )
    (directory / "2_Taken").mkdir()
    name: tuple[int]
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
    check(
        "has children" in str(items.delete_items([(1,)])),
        "delete refuses an item with children",
    )
    check(
        items.delete_items([(1,)], True, lambda question: "n")
        == "Nothing deleted"
        and (directory / "1_Uno_again").is_dir(),
        "delete -r asks first",
    )
    questions: list[str] = []

    def yes(question: str) -> str:
        """Answer yes to a question.

        Arguments:
        * `question` (`str`):
          The question, which is recorded.

        Returns:
        * (`str`): "y".
        """
        questions.append(question)
        return "y"

    result: tuple[list[Item], dict[str, Item]] | str = items.delete_items(
        [(1,)], True, yes
    )
    check(
        not isinstance(result, str)
        and [item.number for item in result[0]] == ["1", "1.1"]
        and list(result[1]) == ["2"]
        and result[1]["2"].number == "1"
        and questions
        == ["Do you really want to delete 2 items Yes(y) or No(n). "]
        and not (directory / "1_Uno_again").exists()
        and not (directory / "1.1_Child").exists()
        and read_file(directory / "1_Two" / "Details.md")
        == "# 1 Two\nNotes\n",
        "delete -r 1 renumbers 2 to 1",
    )
    recursive: bool
    for recursive in (False, True):
        check(
            isinstance(items.delete_items([(9,)], recursive), str),
            f"reject delete 9 recursive={recursive}",
        )
    details_path: Path = directory / "1_Two" / "Details.md"
    details_path.unlink()
    details_path.mkdir()
    check(
        "Unable to rename" in str(items.rename_item((1,), "Deux")),
        "rename failure",
    )
    items.create_item("2", "Three")
    (directory / "2_Three" / "Details.md").unlink()
    (directory / "2_Three" / "Details.md").mkdir()
    check(
        "Unable to renumber" in str(items.delete_items([(1,)]))
        and items.directories[(1,)] == directory / "1_Three",
        "renumber failure",
    )
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    directory.chmod(0o500)
    try:
        check(
            "Unable to delete" in str(items.delete_items([(1,)])),
            "delete failure",
        )
    finally:
        directory.chmod(0o700)


# Function `_test_numbering()`:
def _test_numbering(check: Check, directory: Path) -> None:
    """Test numeric order, ranges, renumbering and fixing gaps.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    items: Items = Items(directory)
    part: int
    for part in range(1, 12):
        items.create_item(str(part), f"Top {part}")
    check(
        [item.number for item in items.list_items()][8:] == ["9", "10", "11"],
        "list in numeric order",
    )
    items.delete_items([(part,) for part in range(4, 12)])
    number: str
    title: str
    for number, title in (
        ("1.1", "B"),
        ("1.2", "C"),
        ("1.2.1", "D"),
        ("1.3", "E"),
        ("1.3.1", "F"),
        ("1.4", "G"),
        ("1.5", "H"),
    ):
        items.create_item(number, title)

    def tree() -> list[str]:
        """Return item 1 and its descendants, reloaded from disk.

        Returns:
        * (`list[str]`): The number and title of each item.
        """
        return [
            f"{item.number} {item.title}"
            for item in Items(directory).list_items((1,))
        ]

    result: tuple[list[Item], dict[str, Item]] | str = items.delete_items(
        [(1, 1)]
    )
    check(
        not isinstance(result, str)
        and [item.title for item in result[0]] == ["B"]
        and {old: item.number for old, item in result[1].items()}
        == {
            "1.2": "1.1",
            "1.2.1": "1.1.1",
            "1.3": "1.2",
            "1.3.1": "1.2.1",
            "1.4": "1.3",
            "1.5": "1.4",
        }
        and tree()
        == [
            "1 Top 1",
            "1.1 C",
            "1.1.1 D",
            "1.2 E",
            "1.2.1 F",
            "1.3 G",
            "1.4 H",
        ]
        and read_file(directory / "1.2.1_F" / "Details.md") == "# 1.2.1 F\n",
        "delete 1.1 renumbers the later items and their children",
    )
    word: str
    message: str
    for word, message in (
        ("1.3-2", "Invalid range"),
        ("1.3-x", "Invalid range"),
        ("x-4", "Invalid item number"),
        ("1.3-9", "'1.5' does not exist"),
    ):
        check(
            message in str(items.resolve_range(word)),
            f"reject range {word!r}",
        )
    check(
        items.resolve_range("N.e") == [(1, 2)]
        and items.resolve_range("1.3-4") == [(1, 3), (1, 4)],
        "resolve a tag and a range",
    )
    items.delete_items([(1, 3), (1, 4)])
    check(
        tree() == ["1 Top 1", "1.1 C", "1.1.1 D", "1.2 E", "1.2.1 F"],
        "delete a range",
    )
    items.create_item("1.3", "G")
    shutil.rmtree(directory / "1.1_C")
    errors: io.StringIO = io.StringIO()
    with contextlib.redirect_stderr(errors):
        check(
            tree() == ["1 Top 1", "1.1 D", "1.2 E", "1.2.1 F", "1.3 G"],
            "fix a gap made by hand",
        )
    check(
        "(1.1 missing); renumbered 1.1.1 -> 1.1" in errors.getvalue(),
        "report a gap made by hand",
    )
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    shutil.rmtree(directory / "2_Top_2")
    (directory / "3_Top_3" / "Details.md").chmod(0o400)
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
        Items(directory)
    check(
        "Unable to renumber" in errors.getvalue(),
        "report a failure to fix a gap",
    )


# Function `_test_moving()`:
def _test_moving(check: Check, directory: Path) -> None:
    """Test creating at a place and moving.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    items: Items = Items(directory)
    number: str
    title: str
    for number, title in (
        ("1", "A"),
        ("1.1", "B"),
        ("1.2", "C"),
        ("2", "D"),
        ("2.1", "E"),
    ):
        items.create_item(number, title)

    def tree() -> str:
        """Return every item, reloaded from disk.

        Returns:
        * (`str`): The number and title of each item, joined by spaces.
        """
        return " ".join(
            f"{item.number}{item.title}"
            for item in Items(directory).list_items()
        )

    check(
        "already exists" in str(items.create_item("1.2", "X"))
        and isinstance(items.create_item("1.3", "X"), Item)
        and isinstance(items.create_item("3", "Y"), Item),
        "create at a free number",
    )
    items.delete_items([(1, 3)])
    items.delete_items([(3,)])
    items.create_item("1.1", "N", "before")
    check(
        tree() == "1A 1.1N 1.2B 1.3C 2D 2.1E"
        and read_file(directory / "1.2_B" / "Details.md") == "# 1.2 B\n",
        "create before 1.1",
    )
    items.create_item("M.n", "F", "after")
    check(tree() == "1A 1.1N 1.2F 1.3B 1.4C 2D 2.1E", "create after 1.1")
    check(
        "does not exist" in str(items.create_item("9", "X", "before"))
        and "empty title" in str(items.create_item("1", "!!", "after"))
        and tree() == "1A 1.1N 1.2F 1.3B 1.4C 2D 2.1E",
        "reject create at a bad place",
    )
    moved: dict[str, Item] | str = items.move_items(
        [(1, 3), (1, 4)], "before", (1, 1)
    )
    check(
        tree() == "1A 1.1B 1.2C 1.3N 1.4F 2D 2.1E"
        and not isinstance(moved, str)
        and {old: item.number for old, item in moved.items()}
        == {"1.1": "1.3", "1.2": "1.4", "1.3": "1.1", "1.4": "1.2"},
        "move a range before 1.1",
    )
    items.move_items([(1, 1)], "after", (2, 1))
    check(tree() == "1A 1.1C 1.2N 1.3F 2D 2.1E 2.2B", "move after 2.1")
    items.move_items([(2,)], "", (1, 4))
    check(
        tree() == "1A 1.1C 1.2N 1.3F 1.4D 1.4.1E 1.4.2B",
        "move to a free number with children",
    )
    bad_moves: list[
        tuple[list[tuple[int, ...]], str, tuple[int, ...], str]
    ] = [
        ([(1,)], "", (1, 5), "into themselves"),
        ([(1, 1)], "before", (1, 1), "before themselves"),
        ([(1, 1)], "", (1, 9), "that is 1.5"),
        ([(1, 1)], "", (5, 1), "'5' does not exist"),
        ([(1, 1)], "after", (9,), "'9' does not exist"),
        ([(1, 1)], "", (1, 2), "already exists"),
        ([(1, 9)], "", (3,), "'1.9' does not exist"),
    ]
    names: list[tuple[int, ...]]
    place: str
    target: tuple[int, ...]
    message: str
    for names, place, target, message in bad_moves:
        check(
            message in str(items.move_items(names, place, target)),
            f"reject move {names} {place} {target}",
        )
    check(
        items.move_items([(1, 1)], "before", (1, 2)) == {},
        "a move to the same place changes nothing",
    )


# Function `_test_recovery()`:
def _test_recovery(check: Check, directory: Path) -> None:
    """Test finishing a renumbering interrupted after every step.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    directory.mkdir()
    interruptions: int = 0
    limit: int
    for limit in range(12):
        collection: Path = directory / f"after_{limit}"
        items: Items = Items(collection)
        # Same titles, so new directory names are old ones.
        number: str
        title: str
        for number, title in (
            ("1", "Notes"),
            ("1.1", "Child"),
            ("2", "Notes"),
        ):
            items.create_item(number, title)
        os.environ[INTERRUPT_VARIABLE] = str(limit)
        interrupted: bool = False
        try:
            items.move_items([(2,)], "before", (1,))
        except RenumberInterrupted:
            interrupted = True
        finally:
            del os.environ[INTERRUPT_VARIABLE]
        interruptions += interrupted
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            reloaded: Items = Items(collection)
        check(
            [(item.number, item.tag) for item in reloaded.list_items()]
            == [("1", "n2"), ("2", "n"), ("2.1", "c")]
            and all(
                read_file(reloaded.directories[item.name] / "Details.md")
                == f"# {item.number} {item.title}\n"
                for item in reloaded.list_items()
            )
            and not (collection / RENUMBER_FILE).exists()
            and not any(collection.glob(".renumber_*"))
            and ("Finished an interrupted" in errors.getvalue())
            == interrupted,
            f"finish a renumbering interrupted after {limit} steps",
        )
    check(interruptions == 9, "a renumbering has nine steps")
    text: str
    message: str
    for text, message in (
        ("{", "Unable to read"),
        ("[]", "not a JSON object"),
        ('{"phase": 2, "renames": [{"old": "x"}]}', "KeyError"),
    ):
        write_file(directory / "after_0" / RENUMBER_FILE, text)
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            Items(directory / "after_0")
        check(
            "Unable to finish an interrupted" in errors.getvalue()
            and message in errors.getvalue(),
            f"report a damaged {RENUMBER_FILE}: {text}",
        )


# Function `_test_references()`:
def _test_references(check: Check, directory: Path) -> None:
    """Test finding and updating references to a renamed tag.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    directory.mkdir()
    items: Items = Items(directory / "TASKS")
    items.create_item("1", "Fix Big Mistake")
    items.create_item("2", "Other Work")
    other: Path = directory / "TASKS" / "2_Other_Work"
    text: str = "See T.fbm, T.fbm2, XT.fbm and `T.fbm`.\n"
    relative: str
    for relative in (
        "notes.md",
        "sub/deep.md",
        ".hidden/skipped.md",
        "other.txt",
        "TASKS/2_Other_Work/Context.md",
        "TASKS/2_Other_Work/.hidden/skipped.md",
    ):
        (directory / relative).parent.mkdir(exist_ok=True)
        write_file(directory / relative, text)
    (directory / "link.md").symlink_to(directory / "notes.md")
    (other / "far").symlink_to(directory / "sub")
    (directory / "LINKED").symlink_to(directory / "TASKS")
    questions: list[str] = []
    answers: list[str] = []

    def ask(question: str) -> str:
        """Answer a question with the next of the answers.

        Arguments:
        * `question` (`str`):
          The question, which is recorded.

        Returns:
        * (`str`): The next answer.

        Raises:
        * `EOFError`: If there are no answers left.
        """
        questions.append(question)
        if not answers:
            raise EOFError
        return answers.pop(0)

    def rename(*words: str) -> str:
        """Rename item 1.

        Arguments:
        * `words` (`str`):
          The words of the new title.

        Returns:
        * (`str`): The error string and everything printed.
        """
        output: io.StringIO = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            error: str = items.rename_command(["1", "to", *words], ask)
        return error + output.getvalue()

    answers[:] = ["y", "n"]
    output: str = rename("Good", "Fix")
    check(
        "searched for old tags; to look elsewhere, use e.g. "
        "`grep -rnwF -e T.fbm .`"
        in output
        and "The following `.md` files have tags that need to be renamed:\n"
        "  TASKS/2_Other_Work/Context.md\n  notes.md\n"
        "Not updated; T.fbm is still used"
        in output
        and questions[-1] == "OK to update them? (y=Yes, n=No) "
        and read_file(directory / "notes.md") == text,
        "list the references to a changed tag and leave them",
    )
    answers[:] = []
    check(
        "following" not in rename("Fix", "Big", "Mistake")
        and "following" not in rename("Fix", "Big", "Mistakes"),
        "no question without references or without a new tag",
    )
    answers[:] = ["yes"]
    output = rename("Good", "Fix")
    updated: str = "See T.gf, T.fbm2, XT.fbm and `T.gf`.\n"
    check(
        "Updated T.fbm to T.gf in 2 files" in output
        and read_file(directory / "notes.md") == updated
        and read_file(other / "Context.md") == updated
        and read_file(directory / "sub" / "deep.md") == text
        and read_file(other / ".hidden" / "skipped.md") == text
        and read_file(directory / ".hidden" / "skipped.md") == text
        and read_file(directory / "other.txt") == text,
        "update the references to a changed tag",
    )
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    (other / "Context.md").chmod(0o444)
    rename("Fix", "Big", "Mistake")
    check(
        tag_references(directory, "T.gf") == [directory / "notes.md"],
        "read-only files are not references",
    )
    (other / "Context.md").chmod(0o644)

    def refuse_writes(question: str) -> str:
        """Make `notes.md` read-only, then answer yes.

        Arguments:
        * `question` (`str`):
          The question.

        Returns:
        * (`str`): "y".
        """
        (directory / "notes.md").chmod(0o444)
        return "y"

    write_file(directory / "notes.md", "T.fbm\n")
    with contextlib.redirect_stdout(io.StringIO()):
        check(
            "Unable to update"
            in items.rename_command(["1", "to", "Good", "Fix"], refuse_writes),
            "report a reference that can not be updated",
        )


# Function `_test_closed()`:
def _test_closed(check: Check, directory: Path) -> None:
    """Test `Summary.md`, `Closed.md` and Closed items in `Startup.md`.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    directory.mkdir()
    tasks: Items = Items(directory / "TASKS")
    issues: Items = Items(directory / "ISSUES")
    number: str
    title: str
    for number, title in (
        ("1", "Alpha"),
        ("2", "Beta"),
        ("3", "Gamma"),
        ("4", "Delta"),
    ):
        tasks.create_item(number, title)
    issues.create_item("1", "Crash")
    check(
        read_file(tasks.directories[(1,)] / "Summary.md")
        == "# Summary of `T.a` Alpha\n"
        and not has_summary(tasks.directories[(1,)]),
        "a new item has an empty Summary.md",
    )
    write_file(
        tasks.directories[(1,)] / "Summary.md",
        "# Summary of `T.a` Alpha\n\nAlpha is done.\n",
    )
    write_file(issues.directories[(1,)] / "Summary.md", "Fixed it.\n")
    check(
        has_summary(tasks.directories[(1,)])
        and has_summary(issues.directories[(1,)]),
        "a Summary.md with more than its heading",
    )
    # Closed in this order, a day apart.
    collection: Items
    name: tuple[int]
    date: int
    for collection, name, date in (
        (tasks, (4,), 1),
        (tasks, (2,), 2),
        (issues, (1,), 3),
        (tasks, (1,), 4),
    ):
        # The issue is Rejected, which counts as finished too.
        collection.set_state(
            name, "Rejected" if collection is issues else "Closed"
        )
        metadata: dict[str, object] = read_item(collection.directories[name])
        history: object = metadata["history"]
        if isinstance(history, list):
            history[-1]["time"] = f"2026-10-0{date}T12:00:00Z"
        write_item(collection.directories[name], metadata)
    saved: str | None = os.environ.pop(SUMMARIES_VARIABLE, None)
    try:
        os.environ[SUMMARIES_VARIABLE] = "3"
        check(write_startup([issues, tasks]) == "", "write Closed.md")
        check(
            read_file(directory / "TASKS" / "Startup.md")
            == "@3_Gamma/Details.md\n@1_Alpha/Summary.md\n"
            "@../ISSUES/1_Crash/Summary.md\n@2_Beta/Details.md\n"
            "@Closed.md\n",
            "Startup.md has the newest summaries, then Closed.md",
        )
        check(
            read_file(directory / "TASKS" / "Closed.md")
            == "# Older Closed and Rejected Items\n\n"
            "<!-- Written by ai_contexts; do not edit. -->\n\n"
            "These items are only listed by tag and title; "
            "`ai_contexts TAG\nshow` shows the rest.\n\n- `T.d` Delta\n",
            "Closed.md lists the older closed items",
        )
        os.environ[SUMMARIES_VARIABLE] = "junk"
        write_startup([issues, tasks])
        check(
            "@4_Delta/Details.md"
            in read_file(directory / "TASKS" / "Startup.md")
            and not (directory / "TASKS" / "Closed.md").exists(),
            f"{CLOSED_SUMMARIES} summaries by default, so no Closed.md",
        )
    finally:
        del os.environ[SUMMARIES_VARIABLE]
        if saved is not None:
            os.environ[SUMMARIES_VARIABLE] = saved  # pragma: no cover
    tasks.rename_item((3,), "Gamma Ray")
    check(
        read_file(tasks.directories[(3,)] / "Summary.md")
        == "# Summary of `T.gr` Gamma Ray\n",
        "rename rewrites the Summary.md heading",
    )
    write_file(tasks.directories[(3,)] / "Summary.md", "Notes.\n")
    tasks.rename_item((3,), "Gamma")
    check(
        read_file(tasks.directories[(3,)] / "Summary.md")
        == "# Summary of `T.g` Gamma\nNotes.\n",
        "rename adds a missing Summary.md heading",
    )
    (tasks.directories[(3,)] / "Summary.md").unlink()
    with contextlib.redirect_stderr(io.StringIO()):
        reloaded: Items = Items(directory / "TASKS")
    check(
        read_file(reloaded.directories[(3,)] / "Summary.md")
        == "# Summary of `T.g` Gamma\n",
        "an item without a Summary.md gets one on load",
    )
    (tasks.directories[(2,)] / "Summary.md").unlink()
    (tasks.directories[(2,)] / "Summary.md").mkdir()
    write_file(tasks.directories[(2,)] / ITEM_FILE, "[]")
    check(
        not has_summary(tasks.directories[(2,)])
        and closed_time(tasks.items[(2,)], tasks.directories[(2,)])
        == tasks.items[(2,)].updated,
        "a closed item without a readable summary or history",
    )
    os.environ[SUMMARIES_VARIABLE] = "1"
    try:
        (directory / "TASKS" / "Closed.md").mkdir()
        check(
            "Unable to write" in write_startup([issues, tasks]),
            "Closed.md can not be written",
        )
    finally:
        del os.environ[SUMMARIES_VARIABLE]
    check(
        "Unable to write" in write_startup([issues, tasks]),
        "Closed.md can not be removed",
    )
    (directory / "TASKS" / "Closed.md").rmdir()
    check(
        write_startup([issues, tasks]) == ""
        and not (directory / "TASKS" / "Closed.md").exists(),
        "no Closed.md without older closed items",
    )
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    (issues.directories[(1,)] / "Summary.md").unlink()
    issues.directories[(1,)].chmod(0o500)
    errors: io.StringIO = io.StringIO()
    try:
        with contextlib.redirect_stderr(errors):
            Items(directory / "ISSUES")
    finally:
        issues.directories[(1,)].chmod(0o700)
    check(
        "Unable to add a summary" in errors.getvalue(),
        "report a Summary.md that can not be added",
    )


# Function `_test_checks()`:
def _test_checks(check: Check, directory: Path) -> None:
    """Test the checks made each time a collection is loaded.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    directory.mkdir()
    items: Items = Items(directory / "TASKS")
    number: str
    title: str
    for number, title in (("1", "A"), ("2", "B"), ("3", "C")):
        items.create_item(number, title)

    def load() -> tuple[Items, str]:
        """Load the TASKS collection.

        Returns:
        * (`tuple[Items, str]`): The collection and the messages printed
          to stderr.
        """
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            loaded: Items = Items(directory / "TASKS")
        return loaded, errors.getvalue()

    check(load()[1] == "", "no messages for a sound collection")
    write_file(items.directories[(1,)] / "Details.md", "# 7 A\nText.\n")
    write_file(items.directories[(2,)] / "Details.md", "Notes only.\n")
    write_file(items.directories[(3,)] / "Details.md", "# 3 Cee\n")
    write_file(
        items.directories[(1,)] / "Summary.md",
        "# Summary of `X.q` Old\nBody\n",
    )
    write_file(items.directories[(2,)] / "Summary.md", "Body only.\n")
    metadata: dict[str, object] = read_item(items.directories[(3,)])
    write_item(items.directories[(3,)], {**metadata, "tag": "a"})
    loaded: Items
    messages: str
    loaded, messages = load()
    check(
        read_file(items.directories[(1,)] / "Details.md") == "# 1 A\nText.\n"
        and "Fixed the item number in the heading of" in messages
        and loaded.items[(1,)].title == "A",
        "fix a wrong number in a Details.md heading",
    )
    check(
        "does not start with a '# 2 TITLE' heading; `ai_contexts T.b rename "
        "to TITLE` adds one" in messages,
        "report a Details.md without a heading",
    )
    check(
        "its directory name does not match its title 'Cee'; `ai_contexts T.a "
        "rename to Cee` fixes it" in messages,
        "report a title that no longer matches the directory",
    )
    check(
        read_file(items.directories[(1,)] / "Summary.md")
        == "# Summary of `T.a` A\nBody\n"
        and read_file(items.directories[(2,)] / "Summary.md")
        == "# Summary of `T.b` B\nBody only.\n"
        and messages.count("Summary.md") == 3,
        "fix Summary.md headings",
    )
    check(
        "Items 1, 3 in '" in messages and "share the tag T.a" in messages,
        "report a shared tag",
    )
    messages = load()[1]
    check(
        "Fixed" not in messages and "share the tag" in messages,
        "fixes are made once; reports repeat until fixed",
    )
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    write_file(items.directories[(1,)] / "Summary.md", "stale\n")
    (items.directories[(1,)] / "Summary.md").chmod(0o400)
    try:
        messages = load()[1]
    finally:
        (items.directories[(1,)] / "Summary.md").chmod(0o600)
    check("Unable to check" in messages, "report a check that fails")


# Function `_test_write_failures()`:
def _test_write_failures(check: Check, directory: Path) -> None:
    """Test failing to write while renumbering or noting the time.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    directory.mkdir()

    def collection(name: str) -> Items:
        """Make a collection with two items.

        Arguments:
        * `name` (`str`):
          The name of the collection.

        Returns:
        * (`Items`): The collection.
        """
        items: Items = Items(directory / name)
        items.create_item("1", "A")
        items.create_item("2", "B")
        return items

    notes: Items = collection("notes")
    (directory / "notes" / COLLECTION_FILE).chmod(0o400)
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        check(
            "Unable to write"
            in notes.rename_command(["1", "to", "Ay"], lambda _: "y")
            and "Unable to write"
            in notes.move_command(["2", "before", "1"], lambda _: "y"),
            "the time of a move or rename can not be saved",
        )
    (directory / "notes" / COLLECTION_FILE).chmod(0o600)
    commands: Items = collection("commands")
    (commands.directories[(2,)] / "Details.md").chmod(0o400)
    (directory / "commands" / "1_Taken").mkdir()

    def yes(_: str) -> str:
        """Answer yes to a question.

        Arguments:
        * `_` (`str`):
          The question, which is ignored.

        Returns:
        * (`str`): "y".
        """
        return "y"

    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        check(
            "Unable to renumber"
            in commands.move_command(["1", "after", "2"], yes)
            and "already exists"
            in commands.rename_command(["1", "to", "Taken"], yes),
            "a confirmed move or rename can still fail",
        )
    marker: Items = collection("marker")
    (directory / "marker").chmod(0o500)
    try:
        check(
            "Unable to renumber"
            in str(marker.move_items([(2,)], "before", (1,)))
            and marker.items[(1,)].title == "A",
            f"no renumbering without {RENUMBER_FILE}",
        )
    finally:
        (directory / "marker").chmod(0o700)
    move: Items = collection("move")
    (move.directories[(2,)] / "Details.md").chmod(0o400)
    check(
        "Unable to renumber" in str(move.move_items([(1,)], "after", (2,))),
        "move can not renumber",
    )
    create: Items = collection("create")
    (create.directories[(1,)] / "Details.md").chmod(0o400)
    check(
        "Unable to renumber" in str(create.create_item("1", "N", "before")),
        "create before can not renumber",
    )


# Function `_test_snapshot_reminder()`:
def _test_snapshot_reminder(
    check: Check, run: Callable[..., tuple[int, str]], answers: list[str]
) -> None:
    """Test the reminder to snapshot before a move or rename.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `run` (`Callable[..., tuple[int, str]]`):
      Runs a command in a directory with a TASKS collection whose item 1
      has one child, and returns its exit code and output.
    * `answers` (`list[str]`):
      The answers to the questions, in turn.
    """
    saved: str | None = os.environ.pop(DELAY_VARIABLE, None)
    try:
        settings: object = json.loads(
            read_file(Path("TASKS") / COLLECTION_FILE)
        )
        check(
            isinstance(settings, dict)
            and local_time(str(settings["last_move_or_rename"]))
            not in ("-", "?"),
            "the time of the last move or rename is saved",
        )
        rename: tuple[str, ...] = ("t", "ren", "1", "to", "An", "item")
        move: tuple[str, ...] = ("t", "mo", "1.1", "1.2")
        check(
            "snapshot" not in run(*rename)[1]
            and "snapshot" not in run(*move)[1],
            "no reminder soon after a move or rename",
        )
        cases: list[tuple[str, list[str], int, str]] = [
            ("0", ["y"], 0, "snapshot"),
            ("0", ["n"], 1, "Not renamed"),
            ("0", [], 1, "Not renamed"),
            ("junk", [], 0, "An item"),
        ]
        delay: str
        given: list[str]
        code: int
        text: str
        for delay, given, code, text in cases:
            os.environ[DELAY_VARIABLE] = delay
            answers[:] = given
            result: tuple[int, str] = run(*rename)
            check(
                result[0] == code and text in result[1],
                f"rename with delay {delay!r} and answers {given}",
            )
        os.environ[DELAY_VARIABLE] = "0"
        answers[:] = ["n"]
        check(run(*move)[1].endswith("Not moved\n"), "a move is refused")
        answers[:] = ["y"]
        check("Nothing moved" in run(*move)[1], "a move goes ahead")
        answers[:] = []
        arguments: tuple[str, str, str, str, str]
        for arguments, text in (
            (("t", "mo", "1", "before", "1"), "before themselves"),
            (("t", "ren", "9", "to", "Nine"), "'9' does not exist"),
            (("t", "ren", "1", "to", "!!"), "empty title"),
        ):
            result = run(*arguments)
            check(
                text in result[1] and "snapshot" not in result[1],
                f"no reminder for a bad command {arguments}",
            )
        del os.environ[DELAY_VARIABLE]
        write_file(
            Path("TASKS") / COLLECTION_FILE,
            '{"last_move_or_rename": "junk"}\n',
        )
        answers[:] = ["y"]
        check(
            "snapshot" in run(*rename)[1],
            "reminder after a damaged time",
        )
    finally:
        if saved is not None:
            os.environ[DELAY_VARIABLE] = saved  # pragma: no cover


# Function `_test_commands()`:
def _test_commands(check: Check, directory: Path) -> None:
    """Test `run_command()` from inside a directory.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    answers: list[str] = []
    questions: list[str] = []

    def ask(question: str) -> str:
        """Answer a question with the next of the answers.

        Arguments:
        * `question` (`str`):
          The question, which is recorded.

        Returns:
        * (`str`): The next answer.

        Raises:
        * `EOFError`: If there are no answers left.
        """
        questions.append(question)
        if not answers:
            raise EOFError
        return answers.pop(0)

    def run(*arguments: str) -> tuple[int, str]:
        """Run an ai_contexts command.

        Arguments:
        * `arguments` (`str`):
          The command line arguments.

        Returns:
        * (`tuple[int, str]`): The exit code and everything printed.
        """
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
        answer: str
        arguments: tuple[str, ...]
        code: int
        text: str
        for answer, arguments, code, text in (
            (
                "",
                (),
                0,
                "0 collections found\n`ai_contexts NAME create` creates",
            ),
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
            ("", ("t", "re", "1"), 1, "reference, reject, rename"),
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
            ("", ("t", "cl", "1.1"), 0, "Closed"),
            ("", ("t", "ls"), 0, "An item\n(1 Closed or Rejected item not"),
            ("", ("t", "ls", "1.1"), 0, "Closed     T.c  Child\n"),
            ("", ("t", "ls", "-a"), 0, "Closed     T.c  Child\n"),
            ("", ("t", "cl", "1"), 0, "Closed"),
            ("", ("t", "ls", "--all", "-l"), 0, "  An item\n1.1"),
            ("", ("t", "rej", "1"), 0, "Rejected"),
            ("", ("t", "ls"), 0, "(2 Closed or Rejected items not shown;"),
            ("", ("t", "sh", "1"), 0, "Rejected\n"),
            ("", ("t", "o", "-r", "1"), 0, "Open"),
            ("", ("t", "cl", "1"), 0, "Closed"),
            ("", ("t", "s", "1"), 1, "show, suspend"),
            ("", ("t", "su", "--recursive", "1"), 0, "1.1"),
            ("", ("t", "o", "-r", "1"), 0, "Open"),
            ("", ("t", "pe", "1.1"), 0, "Pending"),
            ("", ("t", "p", "1.1"), 1, "pending, priority"),
            ("", ("t", "pr", "1", "1"), 1, "Priority is not enabled"),
            ("", ("t", "ls"), 0, "Open       T.i "),
            ("", ("t", "en"), 1, "FEATURE is one of: priority"),
            ("", ("t", "en", "x"), 1, "FEATURE is one of"),
            ("", ("t", "en", "p", "q"), 1, "FEATURE is one of"),
            ("", ("t", "en", "p"), 0, ""),
            ("", ("t", "sh", "1"), 0, "State:     Open\nPriority:  -\n"),
            ("", ("t", "pr", "1.1", "0"), 0, "Pending    0  T.c  Child"),
            ("", ("t", "ls"), 0, "0  T.c  Child\n1    Open       -  T.i"),
            ("", ("t", "pr", "1", "1"), 0, "Open       1  T.i "),
            ("", ("t", "pr", "1", "-"), 0, "Open       -  T.i "),
            ("", ("t", "pr", "1", "4"), 1, "Invalid priority"),
            ("", ("t", "pr", "1"), 1, "Usage"),
            ("", ("t", "pr", "x", "1"), 1, "Invalid"),
            ("", ("t", "pr", "9", "1"), 1, "does not exist"),
            ("", ("t", "pr", "1.1", "-"), 0, "Pending    -  T.c  Child"),
            ("", ("t", "ls"), 0, "-  T.i  An item\n1.1  Pending    -"),
            ("", ("t", "di", "pr"), 0, ""),
            ("", ("t", "ls"), 0, "Open       T.i  An item\n1.1  Pending"),
            ("", ("t", "ref", "1.1"), 0, "Reference"),
            ("", ("t", "open"), 1, "Usage"),
            ("", ("t", "close", "9"), 1, "does not exist"),
            ("", ("t", "close", "x"), 1, "Invalid"),
            ("y", ("t", "ren", "1.1", "to", "New", "child"), 0, "New"),
            ("", ("t", "ren", "1.1", "New", "child"), 1, "Usage"),
            ("", ("t", "rename", "1"), 1, "Usage"),
            ("", ("t", "rename", "x", "to", "y"), 1, "Invalid"),
            ("", ("t", "rename", "9", "to", "Nine"), 1, "does not exist"),
            ("", ("t", "create", "2", "Doomed"), 0, ""),
            ("", ("t", "d", "2"), 1, "delete, disable"),
            ("", ("t", "create", "3", "Survivor"), 0, ""),
            (
                "",
                ("t", "del", "2"),
                0,
                (
                    "Doomed\nRenumbered (old number first):\n"
                    "3 -> 2  Pending    T.s  Survivor\n"
                ),
            ),
            ("", ("t", "del", "T.s"), 0, "Deleted:\n2  Pending"),
            ("", ("t", "delete"), 1, "Usage"),
            ("", ("t", "delete", "x"), 1, "Invalid"),
            ("", ("t", "delete", "-r", "9"), 1, "does not exist"),
            ("", ("t", "delete", "1", "2"), 1, "Usage"),
            ("", ("t", "delete", "1"), 1, "has children"),
            ("", ("t", "delete", "-r", "1"), 1, "Nothing deleted"),
            ("", ("i", "create", "1", "Crash"), 0, ""),
            ("", ("I", "OPEN", "1"), 0, "Open"),
            (
                "",
                (),
                0,
                "2 collections found in '",
            ),
            (
                "",
                (),
                0,
                (
                    ":\n1 - Issues  I.  1 item: 1 Open\n"
                    "2 - TASKS   T.  2 items: 1 Open, 1 Reference\n"
                    "Type: `ai_contexts -h` for more help.\n"
                ),
            ),
            ("", ("i", "ls"), 0, "I.c  Crash"),
            ("", ("I.c", "show"), 0, "Tag:       I.c\nTitle:     Crash"),
            ("", ("i.C", "sh"), 0, "  Open\n\n# 1 Crash\n"),
            ("", ("t", "sh"), 1, "Usage"),
            ("", ("t", "sh", "9"), 1, "'9' does not exist"),
            ("", ("t", "sh", "x"), 1, "Invalid"),
            ("", ("t.I", "ls"), 0, "T.i "),
            ("", ("T.i", "cr", "x"), 1, "can not be used with 'create'"),
            ("", ("T.zz", "show"), 1, "Invalid item number or tag 'T.zz'"),
            ("", ("Z.x", "ls"), 1, "No collection matches 'Z.x'"),
            ("", ("t", "ls", "T.i"), 0, "T.i   An item\n1.1"),
            ("", ("t", "cl", "t.I"), 0, "Closed     T.i "),
            ("", ("t", "o", "i"), 0, "Open       T.i "),
            ("", ("t", "o", "I.c"), 1, "Invalid item number or tag"),
            ("", ("t", "ren", "T.nc", "to", "Newer", "child"), 0, "T.nc "),
            ("", ("t", "ren", "T.nc", "to", "Old", "kid"), 0, "T.ok "),
            ("", ("t", "ren", "t.OK", "to", "New", "child"), 0, "T.nc "),
            ("", ("t", "o", "1..2"), 1, "Invalid item number '1..2'"),
            ("", ("t", "cr", "after", "1", "Second"), 0, ""),
            ("", ("t", "mo", "2", "before", "1"), 0, "\n2   -> 1    "),
            ("", ("t", "mo", "1", "before", "2"), 0, "Nothing moved"),
            ("", ("t", "mo", "1", "before", "1"), 1, "before themselves"),
            ("", ("t", "mo", "1", "9"), 1, "next free number; that is 3"),
            ("", ("t", "mo", "2", "2.1.1"), 1, "into themselves"),
            ("", ("t", "mo", "1"), 1, "Usage"),
            ("", ("t", "mo", "x", "2"), 1, "Invalid"),
            ("", ("t", "mo", "1", "before", "x"), 1, "Invalid"),
            ("", ("t", "mo", "1", "2..3"), 1, "Invalid"),
            ("", ("t", "mo", "2", "before", "1"), 0, "\n1   -> 2    "),
            ("", ("t", "ren", "2", "to", "Second", "item"), 0, "T.si"),
            ("", ("t", "cr", "before", "x", "Bad"), 1, "Invalid"),
            ("", ("t", "cr", "before", "1"), 1, "Usage"),
            ("", ("t", "del", "2"), 0, "Second"),
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
            == f"Create collection directory '{Path.cwd() / 'TASKS'}'? "
            "[y/N] ",
            "ask before creating a collection",
        )
        _test_snapshot_reminder(check, run, answers)
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
            run("Notes", "create")[0] == 0
            and (directory / "Notes" / COLLECTION_FILE).is_file(),
            "create a collection next to the others",
        )
        check(
            "\n2 - Notes   N.  no items\n" in run()[1],
            "an empty collection is listed with no items",
        )
        answers[:] = ["y"]
        code, text = run("tools", "create")
        check(
            code == 1
            and "tag prefix 'T.', which 'TASKS' already has" in text
            and not (directory / "tools").exists(),
            "collections must have different tag prefixes",
        )
        # Only a collection made by hand can clash.
        (directory / "Tools").mkdir()
        write_file(directory / "Tools" / COLLECTION_FILE, "{}\n")
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
                and "@1_An_item/"
                in read_file(directory / "TASKS" / "Startup.md"),
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


# Function `_runner()`:
def _runner(answers: list[str]) -> Callable[..., tuple[int, str]]:
    """Return a function that runs an ai_contexts command.

    Arguments:
    * `answers` (`list[str]`):
      The answers to the command's questions, in turn; a question with
      no answer left gets EOF.

    Returns:
    * (`Callable[..., tuple[int, str]]`): The function, which returns
      the exit code and everything printed.
    """

    def ask(_: str) -> str:
        """Answer a question with the next of the answers.

        Arguments:
        * `_` (`str`):
          The question, which is ignored.

        Returns:
        * (`str`): The next answer.

        Raises:
        * `EOFError`: If there are no answers left.
        """
        if not answers:
            raise EOFError
        return answers.pop(0)

    def run(*arguments: str) -> tuple[int, str]:
        """Run an ai_contexts command.

        Arguments:
        * `arguments` (`str`):
          The command line arguments.

        Returns:
        * (`tuple[int, str]`): The exit code and everything printed.
        """
        output: io.StringIO = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            code: int = Items.run_command(list(arguments), ask)
        return code, output.getvalue()

    return run


# Function `_test_types()`:
def _test_types(check: Check, directory: Path) -> None:
    """Test collection types, and a rules collection.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    answers: list[str] = []
    run: Callable[..., tuple[int, str]] = _runner(answers)
    original: Path = Path.cwd()
    os.chdir(directory)
    (directory / "sources").mkdir()
    write_file(
        directory / "sources" / "Version_Control_Rules.md", "# Use hg\n"
    )
    try:
        answer: str
        arguments: tuple[str, ...]
        code: int
        text: str
        for answer, arguments, code, text in (
            ("y", ("TASKS", "create"), 0, "Created"),
            ("y", ("RULES", "create"), 0, "Created"),
            ("", ("r", "type"), 0, "RULES: items\n"),
            ("", ("r", "type", "x"), 1, "TYPE is one of: items, rules"),
            ("", ("r", "type", "r", "x"), 1, "Usage"),
            ("", ("r", "type", "r"), 0, "RULES: rules\n"),
            ("", ("r", "type", "rules"), 0, "RULES: rules\n"),
            (
                "",
                ("r", "cr", "1", "sources/Version_Control_Rules.md"),
                0,
                "1  InActive   R.vcr  Version Control Rules\n",
            ),
            ("", ("r", "ls"), 0, "1  InActive   R.vcr  Version Control"),
            ("", ("r", "act", "1"), 0, "1  Active     R.vcr"),
            ("", ("R.vcr", "deact"), 0, "1  InActive   R.vcr"),
            ("", ("r", "a", "R.vcr"), 0, "Active"),
            ("", ("r", "open", "1"), 1, "commands are: create, rename"),
            ("", ("r", "open", "1"), 1, "activate, deactivate"),
            ("", ("r", "d", "1"), 1, "deactivate, delete, disable"),
            ("", ("t", "act", "1"), 1, "Unknown command 'act'"),
            ("", ("t", "d", "1"), 1, "delete, disable\n"),
            ("", ("r", "type", "items"), 1, "only be changed while it has"),
            ("", ("r", "type"), 0, "RULES: rules\n"),
            (
                "",
                ("r", "sh", "1"),
                0,
                "State:     Active\nSource:    sources/Version_Control_Rules",
            ),
            ("", ("t", "cr", "1", "A task"), 0, ""),
            ("", ("t", "o", "1"), 0, "Open"),
            ("", ("t", "type", "i"), 0, "TASKS: items\n"),
            ("", (), 0, "RULES  R.  1 item: 1 Active\n"),
            ("y", ("r", "ren", "1", "to", "Version Rules"), 0, "R.vr"),
        ):
            answers[:] = [answer] if answer else []
            result: tuple[int, str] = run(*arguments)
            check(
                result[0] == code and text in result[1],
                f"type command {' '.join(arguments)!r}",
            )
        rule: Path = directory / "RULES" / "1_Version_Rules"
        check(
            sorted(path.name for path in rule.iterdir())
            == [ITEM_FILE, "Details.md", "Version_Control_Rules.md"],
            "a rule has only a Details.md and its copy",
        )
        check(
            json.loads(read_file(directory / "RULES" / COLLECTION_FILE))[
                "type"
            ]
            == "rules",
            "the type is kept in .ai_contexts.json",
        )
        check(
            read_file(directory / "TASKS" / "Startup.md")
            == "@1_A_task/Details.md\n@1_A_task/Context.md\n",
            "rules are not in Startup.md",
        )
        metadata: dict[str, object] = read_item(rule)
        write_item(rule, {**metadata, "state": "Open"})
        code, text = run("r", "ls")
        check(
            code == 0
            and "its state 'Open' is not one of Active, InActive" in text
            and "R.vr" not in text,
            "skip a rule in a state of another type",
        )
        write_item(rule, metadata)
        settings_path: Path = directory / "RULES" / COLLECTION_FILE
        settings: str = read_file(settings_path)
        problem: str
        for text, problem in (
            ('{"version": "0.1", "type": "bogus"}', "the unknown type"),
            ("[]", "not a JSON object"),
            ("{", "Unable to read"),
        ):
            write_file(settings_path, text)
            output: str
            code, output = run("r", "ls")
            check(
                code == 1 and problem in output,
                f"a collection with the settings {text!r}",
            )
        write_file(settings_path, settings)
        if os.geteuid() == 0:
            # Permissions are not enforced for root.
            return  # pragma: no cover
        settings_path.chmod(0o000)
        try:
            code, text = run("r", "ls")
            check(
                code == 1 and "Unable to read" in text,
                "a collection whose settings can not be read",
            )
        finally:
            settings_path.chmod(0o600)
        empty: Path = directory / "Empty" / COLLECTION_FILE
        empty.parent.mkdir()
        write_file(empty, f'{{"version": "{FORMAT_VERSION}"}}\n')
        empty.chmod(0o400)
        try:
            code, text = run("e", "type", "rules")
            check(
                code == 1 and "Unable to write" in text,
                "a type that can not be saved",
            )
        finally:
            empty.chmod(0o600)
    finally:
        os.chdir(original)


# Function `_test_rules()`:
def _test_rules(check: Check, directory: Path) -> None:
    """Test the rules of a rules collection, with their sources.

    The collections are in `directory/project` and the sources in
    `directory/shared`.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    answers: list[str] = []
    run: Callable[..., tuple[int, str]] = _runner(answers)
    project: Path = directory / "project"
    shared: Path = directory / "shared"
    project.mkdir()
    shared.mkdir()
    (directory / "linked").symlink_to("shared")
    write_file(shared / "Alpha_Rule.md", "# A\n\nAlways do A.\n")
    write_file(shared / "Beta_Rule.md", "# B\n")
    write_file(shared / "Details.md", "# Not a rule\n")
    name: str
    for name in ("other.md", "last.md", "code.md", "fenced.md"):
        write_file(shared / name, "# Imported\n")
    (shared / "Link_Rule.md").symlink_to("Alpha_Rule.md")
    original: Path = Path.cwd()
    os.chdir(project)
    rules: Path = project / "RULES"
    active: Path = rules / "Active_Rules.md"
    try:
        answer: str
        arguments: tuple[str, ...]
        code: int
        text: str
        for answer, arguments, code, text in (
            ("y", ("TASKS", "create"), 0, "Created"),
            ("y", ("RULES", "create"), 0, "Created"),
            ("", ("r", "type", "rules"), 0, "RULES: rules"),
            ("", ("r", "cr", "1"), 1, "NUMBER FILE..."),
            ("", ("t", "cr", "1"), 1, "NUMBER TITLE..."),
            ("", ("r", "cr", "1", "../shared/*.zz"), 1, "No files match"),
            ("", ("r", "cr", "1", "../shared/No.md"), 1, "is not a file"),
            ("", ("r", "cr", "2", "../shared/Beta_Rule.md"), 1, "leave a gap"),
            (
                "",
                ("r", "cr", "1", "../shared/[AB]*_Rule.md"),
                0,
                (
                    "1  InActive   R.ar  Alpha Rule\n"
                    "2  InActive   R.br  Beta Rule\n"
                ),
            ),
            (
                "",
                ("r", "cr", "before", "1", "../linked/Link_Rule.md"),
                0,
                "1  InActive   R.lr  Link Rule\n",
            ),
            ("", ("r", "cr", "4", "../shared/Details.md"), 1, "can not be"),
            ("", ("r", "del", "4"), 0, "Deleted"),
        ):
            answers[:] = [answer] if answer else []
            result: tuple[int, str] = run(*arguments)
            check(
                result[0] == code and text in result[1],
                f"rules command {' '.join(arguments)!r}",
            )
        rule: Path = rules / "2_Alpha_Rule"
        copy: Path = rule / "Alpha_Rule.md"
        metadata: dict[str, object] = read_item(rule)
        check(
            metadata["source"] == "../shared/Alpha_Rule.md"
            and metadata["sha256"]
            == hashlib.sha256(b"# A\n\nAlways do A.\n").hexdigest()
            and read_file(copy) == "# A\n\nAlways do A.\n"
            and copy.stat().st_mode & 0o777 == 0o444,
            "a rule's source is copied, read-only",
        )
        check(
            read_item(rules / "1_Link_Rule")["source"]
            == "../shared/Link_Rule.md"
            and read_file(rules / "1_Link_Rule" / "Link_Rule.md")
            == read_file(copy),
            "a source's directories are resolved, but not its file",
        )
        check(read_file(active) == "", "no Active rules")
        check(
            run("r", "act", "2")[0] == 0
            and read_file(active) == "@2_Alpha_Rule/Alpha_Rule.md\n",
            "Active_Rules.md imports the Active rules",
        )
        check(
            run("r", "act", "-r", "1")[0] == 0
            and read_file(active)
            == "@1_Link_Rule/Link_Rule.md\n@2_Alpha_Rule/Alpha_Rule.md\n",
            "Active_Rules.md is in number order",
        )
        check(
            "@" not in read_file(project / "TASKS" / "Startup.md"),
            "rules are not in Startup.md",
        )
        code, text = run("r", "sh", "R.ar")
        check(
            code == 0
            and "Source:    ../shared/Alpha_Rule.md\nSHA-256:   " in text
            and "Refreshed: 2" in text,
            "show a rule's source",
        )
        write_file(shared / "Alpha_Rule.md", "# A\n\nAlways do A twice.\n")
        code, text = run("r", "ls")
        check(
            "Refreshed R.ar from '../shared/Alpha_Rule.md'" in text
            and "Refreshed R.lr from '../shared/Link_Rule.md'" in text
            and "twice" in read_file(copy),
            "a changed source is copied again",
        )
        code, text = run("r", "ls")
        check("Refreshed" not in text, "an unchanged source is not copied")
        check(
            run("r", "refresh", "2") == (0, "R.ar is up to date\n"),
            "refresh an unchanged rule",
        )
        copy.chmod(0o644)
        write_file(copy, "# A\n\nEdited.\n")
        write_file(shared / "Alpha_Rule.md", "# A\n\nAlways do A thrice.\n")
        code, text = run("r", "ls")
        check(
            "R.ar: its copy '" in text
            and "was edited in place; `ai_contexts R.ar refresh`" in text
            and read_file(copy) == "# A\n\nEdited.\n",
            "an edited copy is left alone",
        )
        check(
            run("r", "refresh", "R.ar")[1].endswith("Not refreshed\n"),
            "refresh an edited copy, with no answer",
        )
        answers[:] = ["n"]
        code, text = run("r", "refresh", "R.ar")
        check(
            code == 1
            and text.endswith("Not refreshed\n")
            and read_file(copy) == "# A\n\nEdited.\n",
            "refresh an edited copy, answering no",
        )
        answers[:] = ["y"]
        code, text = run("r", "refresh", "R.ar")
        check(
            code == 0
            and text.endswith(
                "Refreshed R.ar from '../shared/Alpha_Rule.md'\n"
            )
            and "thrice" in read_file(copy),
            "refresh an edited copy, answering yes",
        )
        metadata = read_item(rule)
        del metadata["sha256"]
        write_item(rule, metadata)
        code, text = run("r", "ls")
        check(
            "Refreshed" not in text
            and "edited" not in text
            and read_item(rule)["sha256"] == sha256_of(copy),
            "record the hash of a copy that matches its source",
        )
        for answer, arguments, code, text in (
            ("", ("r", "refresh"), 1, "Usage"),
            ("", ("r", "refresh", "x"), 1, "Invalid"),
            ("", ("r", "refresh", "9"), 1, "does not exist"),
            ("", ("r", "source", "1"), 1, "Usage"),
            ("", ("r", "source", "x", "y"), 1, "Invalid"),
            ("", ("r", "source", "9", "../shared/Beta_Rule.md"), 1, "exist"),
            ("", ("r", "source", "1", "../shared/No.md"), 1, "not a file"),
            ("", ("r", "source", "1", "../shared/Details.md"), 1, "can not"),
            (
                "",
                ("R.lr", "source", "../shared/Beta_Rule.md"),
                0,
                "1  Active     R.lr  Link Rule\n",
            ),
            ("", ("t", "source", "1", "x"), 1, "Unknown command"),
        ):
            answers[:] = [answer] if answer else []
            result = run(*arguments)
            check(
                result[0] == code and text in result[1],
                f"rules command {' '.join(arguments)!r}",
            )
        check(
            sorted(path.name for path in (rules / "1_Link_Rule").iterdir())
            == [ITEM_FILE, "Beta_Rule.md", "Details.md"]
            and read_file(active)
            == "@1_Link_Rule/Beta_Rule.md\n@2_Alpha_Rule/Alpha_Rule.md\n",
            "a new source replaces the old copy",
        )
        write_file(
            shared / "Beta_Rule.md",
            "# B\n\nSee @other.md and `@code.md`, mail a@b.c.\n"
            "```\n@fenced.md\n```\n@last.md @dataclass\n",
        )
        write_file(project / "CLAUDE.md", "@../shared/Alpha_Rule.md\n@No.md\n")
        code, text = run("r", "ls")
        check(
            "R.lr: its copy imports @other.md (line 3); a rule must stand"
            in text
            and "R.lr: its copy imports @last.md (line 7)" in text
            and "code.md" not in text
            and "b.c" not in text
            and "fenced" not in text
            and "dataclass" not in text,
            "report @ imports in a copy",
        )
        check(
            "R.ar is the same as '../shared/Alpha_Rule.md', which CLAUDE.md "
            "also imports" in text,
            "report a rule that CLAUDE.md also imports",
        )
        (shared / "Beta_Rule.md").unlink()
        code, text = run("r", "ls")
        check(
            "R.lr: its source '../shared/Beta_Rule.md' is missing; its last "
            "copy is kept" in text,
            "a missing source keeps its copy",
        )
        (rules / "1_Link_Rule" / "Beta_Rule.md").unlink()
        code, text = run("r", "ls")
        check(
            "R.lr: its source '../shared/Beta_Rule.md' is missing\n" in text
            and "R.lr is Active but has no copy of its source" in text
            and read_file(active) == "@2_Alpha_Rule/Alpha_Rule.md\n",
            "an Active rule without a copy",
        )
        check(run("r", "refresh", "1")[0] == 1, "refresh a missing source")
        check(
            "has no copy of a source to make Active" in run("r", "act", "1")[1]
            and run("r", "deact", "1")[0] == 0,
            "only a rule with a copy can be made Active",
        )
        metadata = read_item(rules / "1_Link_Rule")
        key: str
        for key in ("source", "sha256", "refreshed"):
            del metadata[key]
        write_item(rules / "1_Link_Rule", metadata)
        code, text = run("r", "ls")
        check(
            "R.lr has no source; `ai_contexts R.lr source PATH` sets one"
            in text,
            "report a rule without a source",
        )
        check(
            "has no source" in run("r", "refresh", "1")[1]
            and "has no copy" in run("r", "act", "1")[1],
            "refresh or activate a rule without a source",
        )
        code, text = run("r", "sh", "1")
        check(
            "Source:    -\nSHA-256:   -\nRefreshed: -\n" in text,
            "show a rule without a source",
        )
        _test_rule_failures(check, run, rules)
    finally:
        os.chdir(original)


# Function `_test_rule_failures()`:
def _test_rule_failures(
    check: Check, run: Callable[..., tuple[int, str]], rules: Path
) -> None:
    """Test rules when files can not be read or written.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `run` (`Callable[..., tuple[int, str]]`):
      Runs a command in the project, and returns its exit code and
      output.
    * `rules` (`Path`):
      The rules collection; rule 2 (`R.ar`) has a source.
    """
    active: Path = rules / "Active_Rules.md"
    active.unlink()
    active.mkdir()
    code: int
    text: str
    code, text = run("r", "ls")
    check(
        code == 1 and "Unable to write" in text,
        "Active_Rules.md can not be written",
    )
    active.rmdir()
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    rule: Path = rules / "2_Alpha_Rule"
    copy: Path = rule / "Alpha_Rule.md"
    copy.chmod(0o000)
    try:
        code, text = run("r", "ls")
        check(
            "Unable to refresh R.ar" in text
            and "Unable to check R.ar" in text,
            "a copy that can not be read",
        )
    finally:
        copy.chmod(0o444)
    (rule / ".copy.tmp" / "x").mkdir(parents=True)
    code, text = run("r", "source", "2", "../shared/Alpha_Rule.md")
    check(
        code == 1 and "Unable to refresh R.ar" in text,
        "a copy that can not be written",
    )
    shutil.rmtree(rule / ".copy.tmp")
    (rule / ITEM_FILE).chmod(0o400)
    try:
        code, text = run("r", "source", "2", "../shared/Alpha_Rule.md")
        check(
            code == 1 and "Unable to set the source of R.ar" in text,
            "a source that can not be recorded",
        )
    finally:
        (rule / ITEM_FILE).chmod(0o600)
    check(
        run("r", "source", "2", "../shared/Alpha_Rule.md")[0] == 0
        and copy.is_file(),
        "set a source again after failures",
    )


# Function `_test_transfer()`:
def _test_transfer(check: Check, directory: Path) -> None:
    """Test `transfer`, which moves items between collections.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    answers: list[str] = []
    run: Callable[..., tuple[int, str]] = _runner(answers)
    original: Path = Path.cwd()
    os.chdir(directory)
    tasks: Path = directory / "TASKS"
    issues: Path = directory / "ISSUES"
    try:
        answer: str
        arguments: tuple[str, ...]
        code: int
        text: str
        for answer, arguments, code, text in (
            ("y", ("TASKS", "create"), 0, "Created"),
            ("y", ("ISSUES", "create"), 0, "Created"),
            ("y", ("RULES", "create"), 0, "Created"),
            ("", ("r", "type", "rules"), 0, ""),
            ("", ("i", "enable", "priority"), 0, ""),
            ("", ("t", "cr", "1", "First bug"), 0, ""),
            ("", ("t", "cr", "1.1", "Child one"), 0, ""),
            ("", ("t", "cr", "2", "Second"), 0, ""),
            ("", ("t", "cr", "3", "Third"), 0, ""),
            ("", ("i", "cr", "1", "Fix bad memory"), 0, ""),
            ("", ("i", "cr", "2", "Something"), 0, ""),
            ("", ("i", "pr", "2", "1"), 0, ""),
            ("", ("t", "tr"), 1, "Usage"),
            ("", ("t", "tr", "1"), 1, "Usage"),
            ("", ("t", "tr", "1", "i", "x", "2"), 1, "Usage"),
            ("", ("t", "tr", "x", "i"), 1, "Invalid"),
            ("", ("t", "tr", "1", "x"), 1, "does not match one collection"),
            ("", ("t", "tr", "1", "t"), 1, "their own collection; use move"),
            ("", ("t", "tr", "1", "r"), 1, "(type items) to 'RULES' (type"),
            ("", ("t", "tr", "9", "i"), 1, "does not exist"),
            ("", ("t", "tr", "1", "i", "5"), 1, "next free number; that is 3"),
            ("", ("t", "tr", "1", "i", "x.y"), 1, "Invalid"),
            ("", ("t", "tr", "1", "i", "after", "I.x"), 1, "Invalid"),
            ("n", ("t", "tr", "1", "i", "before", "2"), 1, "Not transferred"),
            (
                "y",
                ("t", "tr", "T.fb", "i", "before", "I.s"),
                0,
                (
                    "Transferred (old tag first):\n"
                    "T.fb -> 2    Pending    -  I.fb  First bug\n"
                    "T.co -> 2.1  Pending    -  I.co  Child one\n"
                    "In TASKS:\nRenumbered (old number first):\n"
                    "2 -> 1  Pending    T.s  Second\n"
                    "3 -> 2  Pending    T.t  Third\n"
                    "In ISSUES:\nRenumbered (old number first):\n"
                    "2 -> 3  Pending    1  I.s  Something\n"
                ),
            ),
            (
                "y",
                ("T.s", "transfer", "issues"),
                0,
                "T.s -> 4  Pending    -  I.s2  Second\n",
            ),
            ("y", ("i", "tr", "3", "t", "1"), 1, "Item '1' already exists"),
            (
                "y",
                ("i", "tr", "3", "t", "after", "1"),
                0,
                "I.s -> 2  Pending    T.s  Something\n",
            ),
            (
                "y",
                ("i", "tr", "2-3", "t", "before", "T.t"),
                0,
                (
                    "I.fb -> 1    Pending    T.fb  First bug\n"
                    "I.co -> 1.1  Pending    T.co  Child one\n"
                    "I.s2 -> 2    Pending    T.s2  Second\n"
                ),
            ),
            ("", ("i", "ls"), 0, "1  Pending    -  I.fbm  Fix bad memory\n"),
            (
                "",
                ("t", "ls"),
                0,
                (
                    "3    Pending    T.t   Third\n"
                    "4    Pending    T.s   Something\n"
                ),
            ),
            (
                "",
                ("t", "sh", "T.fb"),
                0,
                "Transfers:\n  2",
            ),
            ("y", ("t", "tr", "T.s", "i"), 0, "T.s -> 2  Pending    1  I.s "),
        ):
            answers[:] = [answer] if answer else []
            result: tuple[int, str] = run(*arguments)
            check(
                result[0] == code and text in result[1],
                f"transfer command {' '.join(arguments)!r}",
            )
        moved: Path = tasks / "1_First_bug"
        moves: object = read_item(moved)["moves"]
        check(
            read_file(moved / "Details.md") == "# 1 First bug\n"
            and read_file(tasks / "1.1_Child_one" / "Details.md")
            == "# 1.1 Child one\n"
            and read_file(moved / "Summary.md")
            == "# Summary of `T.fb` First bug\n"
            and isinstance(moves, list)
            and [move["to"] for move in moves] == ["I.fb", "T.fb"],
            "a transfer fixes the headings and records the moves",
        )
        check(
            read_file(tasks / "Startup.md").count("@../ISSUES/") == 2,
            "Startup.md follows a transfer",
        )
        check(
            isinstance(
                Items(tasks).transfer_items([(9,)], Items(issues), "", "3"),
                str,
            ),
            "transfer_items() checks the transfer",
        )
        _test_transfer_failures(check, run, answers, tasks, issues)
    finally:
        os.chdir(original)


# Function `_test_transfer_failures()`:
def _test_transfer_failures(
    check: Check,
    run: Callable[..., tuple[int, str]],
    answers: list[str],
    tasks: Path,
    issues: Path,
) -> None:
    """Test `transfer` when files can not be read or written.

    An interrupted transfer is finished by the next command.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `run` (`Callable[..., tuple[int, str]]`):
      Runs a command next to the collections, and returns its exit code
      and output.
    * `answers` (`list[str]`):
      The answers to the questions, in turn.
    * `tasks` (`Path`):
      The TASKS collection (First bug and its child, Second and Third).
    * `issues` (`Path`):
      The ISSUES collection (Fix bad memory and Something).
    """

    def where(collection: Path, title: str) -> Path:
        """Return the directory of an item, by its title.

        Arguments:
        * `collection` (`Path`):
          The collection.
        * `title` (`str`):
          The item's title, as in its directory name.

        Returns:
        * (`Path`): The item's directory.
        """
        return next(collection.glob(f"*_{title}"))

    bad: Path = tasks.parent / "Bad"
    bad.mkdir()
    write_file(bad / COLLECTION_FILE, "[]\n")
    check(
        "'Bad' can not be loaded" in run("t", "tr", "1", "b")[1],
        "transfer to a collection that can not be loaded",
    )
    shutil.rmtree(bad)
    marker: Path = tasks / ".transfer.json"
    text: str
    for text in ("[]", '{"phase": 1}', '{"phase": "x", "items": []}'):
        write_file(marker, text)
        check(
            "Unable to finish an interrupted transfer: Unable to read"
            in run("t", "ls")[1],
            f"a transfer plan {text!r} that can not be read",
        )
    marker.unlink()
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    collection: Path
    title: str
    file_name: str
    arguments: tuple[str, ...]
    finished: str
    for collection, title, file_name, arguments, finished in (
        (
            issues,
            "Something",
            "Details.md",
            ("T.fb", "i", "before", "I.s"),
            "T.fb -> I.fb, T.co -> I.co",
        ),
        (tasks, "Second", ITEM_FILE, ("T.s2", "i"), "T.s2 -> I.s2"),
        # Moving a directory to another one needs write access to it.
        (tasks, "Third", "", ("T.t", "i"), "T.t -> I.t"),
    ):
        # The directories are found by title, since they are renumbered.
        path: Path = where(collection, title) / file_name
        path.chmod(0o500 if path.is_dir() else 0o400)
        answers[:] = ["y"]
        try:
            code: int
            output: str
            code, output = run("t", "tr", *arguments)
        finally:
            # A renumbering may have moved the file before it failed.
            found: Path
            for found in [path, *tasks.parent.rglob(path.name)]:
                if found.exists():
                    found.chmod(0o700 if found.is_dir() else 0o600)
        check(
            code == 1 and "Unable to" in output,
            f"transfer {' '.join(arguments)} when {path.name} can not be "
            "written",
        )
        code, output = run("i", "ls")
        check(
            code == 0
            and "Finished an interrupted transfer from 'TASKS' to "
            f"'ISSUES': {finished}\n"
            in output,
            f"finish the transfer {' '.join(arguments)}",
        )
    check(
        sorted(path.name for path in issues.glob("[0-9]*"))
        == [
            "1_Fix_bad_memory",
            "2.1_Child_one",
            "2_First_bug",
            "3_Something",
            "4_Second",
            "5_Third",
        ]
        and not any(tasks.glob("[0-9]*")),
        "finished transfers leave no gaps",
    )
    (issues / COLLECTION_FILE).chmod(0o400)
    answers[:] = ["y"]
    try:
        code, output = run("i", "tr", "I.t", "t")
    finally:
        (issues / COLLECTION_FILE).chmod(0o600)
    check(
        code == 1 and "Unable to write" in output,
        "a transfer whose time can not be saved",
    )
    notes: Path = tasks.parent / "notes.md"
    write_file(notes, "Fix I.fb and its child I.co, not I.fbx.\n")
    answers[:] = ["y", "y"]
    code, output = run("i", "tr", "I.fb", "t")
    check(
        code == 0
        and "have tags that need to be renamed:\n  notes.md\n" in output
        and "Updated I.fb to T.fb, I.co to T.co in 1 files" in output
        and read_file(notes) == "Fix T.fb and its child T.co, not I.fbx.\n",
        "a transfer updates the references to every old tag",
    )
    answers[:] = ["n"]
    code, output = run("t", "tr", "T.fb", "i")
    check(
        code == 0
        and "Not updated; T.fb, T.co are still used in them" in output
        and "T.fb" in read_file(notes),
        "a transfer that does not update the references",
    )


# Function `_test_transfer_recovery()`:
def _test_transfer_recovery(check: Check, directory: Path) -> None:
    """Test finishing a transfer interrupted after each of its steps.

    Transferring TASKS item 1 before ISSUES item 2 renumbers both
    collections; transferring TASKS item 3 (with its child) to the end
    of ISSUES renumbers neither, so it can be interrupted between items.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    name: tuple[int]
    place: str
    word: str
    expected: list[str]
    for name, place, word, expected in (
        (
            (1,),
            "before",
            "2",
            [
                "ISSUES/1_Fix_bad_memory # 1 Fix bad memory I.fbm",
                "ISSUES/2.1_Child_one # 2.1 Child one I.co",
                "ISSUES/2_First_bug # 2 First bug I.fb",
                "ISSUES/3_Something # 3 Something I.s",
                "TASKS/1_Second # 1 Second T.s",
                "TASKS/2_Third # 2 Third T.t",
                "TASKS/2.1_Fourth # 2.1 Fourth T.f",
            ],
        ),
        (
            (3,),
            "",
            "3",
            [
                "ISSUES/1_Fix_bad_memory # 1 Fix bad memory I.fbm",
                "ISSUES/2_Something # 2 Something I.s",
                "ISSUES/3.1_Fourth # 3.1 Fourth I.f",
                "ISSUES/3_Third # 3 Third I.t",
                "TASKS/1.1_Child_one # 1.1 Child one T.co",
                "TASKS/1_First_bug # 1 First bug T.fb",
                "TASKS/2_Second # 2 Second T.s",
            ],
        ),
    ):
        _test_interrupted_transfer(
            check,
            directory / f"{name[0]}",
            name,
            place,
            word,
            sorted(expected),
        )
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    parent: Path = directory / "1" / "0"
    parent.chmod(0o300)
    try:
        check(
            not Items(parent / "TASKS").error,
            "load a collection whose parent can not be listed",
        )
    finally:
        parent.chmod(0o700)


# Function `_test_interrupted_transfer()`:
def _test_interrupted_transfer(
    check: Check,
    directory: Path,
    name: tuple[int, ...],
    place: str,
    word: str,
    expected: list[str],
) -> None:
    """Interrupt a transfer of a TASKS item after each step.

    Each time, the next load must finish the transfer.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    * `name` (`tuple[int, ...]`):
      The name of the TASKS item to transfer.
    * `place` (`str`):
      "", "before" or "after".
    * `word` (`str`):
      The number of the place in ISSUES.
    * `expected` (`list[str]`):
      The ISSUES items after the transfer.
    """
    directory.mkdir()
    limit: int
    for limit in range(100):
        root: Path = directory / str(limit)
        root.mkdir()
        tasks: Items = Items(root / "TASKS")
        issues: Items = Items(root / "ISSUES")
        collection: Items
        number: str
        title: str
        for collection, number, title in (
            (tasks, "1", "First bug"),
            (tasks, "1.1", "Child one"),
            (tasks, "2", "Second"),
            (tasks, "3", "Third"),
            (tasks, "3.1", "Fourth"),
            (issues, "1", "Fix bad memory"),
            (issues, "2", "Something"),
        ):
            collection.create_item(number, title)
        os.environ[INTERRUPT_VARIABLE] = str(limit)
        interrupted: bool = False
        try:
            tasks.transfer_items([name], issues, place, word)
        except RenumberInterrupted:
            interrupted = True
        finally:
            del os.environ[INTERRUPT_VARIABLE]
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            Items(root / "TASKS")
        tree: list[str] = sorted(
            f"{path.parent.name}/{path.name} "
            f"{read_file(path / 'Details.md').strip()} "
            f"{path.parent.name[0]}.{read_item(path)['tag']}"
            for path in root.glob("*/[0-9]*")
        )
        check(
            tree == expected
            and not any(root.glob("*/.*_[0-9]*"))
            and not any(root.glob("*/.transfer.json"))
            and not any(root.glob("*/.renumber.json"))
            and ("Finished an interrupted transfer" in errors.getvalue())
            == interrupted,
            f"finish a transfer of {name} interrupted after {limit} steps",
        )
        if not interrupted:
            break
    check(limit > 3, f"a transfer of {name} has several steps")


# Function `_test_errors()`:
def _test_errors(check: Check, directory: Path) -> None:
    """Test the error paths for files that can not be read or written.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
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
    check(
        "Unable to read item '1'" in items.show_command(["1"]),
        "show a damaged item",
    )
    check(
        "Unable to write" in str(items.set_priority((1,), 2)),
        "set_priority write failure",
    )
    (directory / "TASKS" / "Startup.md").mkdir()
    check(
        "Unable to write" in write_startup([items]),
        "write_startup failure",
    )
    text: str
    message: str
    for text, message in (
        ("{", "Unable to read"),
        ("[]", "not a JSON object"),
    ):
        bad: Path = directory / "bad_collection"
        bad.mkdir(exist_ok=True)
        write_file(bad / COLLECTION_FILE, text)
        with contextlib.redirect_stderr(io.StringIO()):
            check(
                message in Items(bad).error,
                f"reject .ai_contexts.json {text!r}",
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
    write_file(read_only / COLLECTION_FILE, "{}\n")
    (read_only / COLLECTION_FILE).chmod(0o400)
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
        collection: Items = Items(read_only)
    check(
        "Unable to write" in errors.getvalue()
        and "version" not in collection.settings,
        "the version can not be added",
    )
    check(
        "Unable to write" in collection.set_feature("priority", True),
        "set_feature write failure",
    )
    (read_only / COLLECTION_FILE).chmod(0o600)
    untagged: Path = read_only / "1_Untagged"
    untagged.mkdir()
    write_item(untagged, new_metadata("Open", "2026-01-01T00:00:00Z"))
    write_file(untagged / "Details.md", "# 1 Untagged\n")
    (untagged / ITEM_FILE).chmod(0o400)
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
        items = Items(read_only)
    check(
        "Unable to add tag" in errors.getvalue()
        and items.items[(1,)].tag == "",
        "add_missing_tags write failure",
    )


# Function `_test_old_collection_file()`:
def _test_old_collection_file(check: Check, directory: Path) -> None:
    """Test the migration of `.tracker.json` to `.ai_contexts.json`.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    name: str
    for name in ("TASKS", "ISSUES", "plain"):
        (directory / name).mkdir()
    write_file(directory / "TASKS" / OLD_COLLECTION_FILE, '{"a": 1}\n')
    write_file(directory / "ISSUES" / COLLECTION_FILE, "{}\n")
    check(
        find_collections(directory / "plain")
        == [directory / "ISSUES", directory / "TASKS"],
        "find collections in the old and new formats",
    )
    check(
        read_file(directory / "TASKS" / COLLECTION_FILE) == '{"a": 1}\n'
        and not (directory / "TASKS" / OLD_COLLECTION_FILE).exists(),
        "rename an old .tracker.json",
    )
    # An old file next to a new one is left alone.
    write_file(directory / "ISSUES" / OLD_COLLECTION_FILE, "[]\n")
    find_collections(directory)
    check(
        read_file(directory / "ISSUES" / COLLECTION_FILE) == "{}\n"
        and (directory / "ISSUES" / OLD_COLLECTION_FILE).is_file(),
        "keep a new .ai_contexts.json over an old .tracker.json",
    )
    if os.geteuid() == 0:
        return  # pragma: no cover
    locked: Path = directory / "locked" / "NOTES"
    locked.mkdir(parents=True)
    write_file(locked / OLD_COLLECTION_FILE, "{}\n")
    locked.chmod(0o500)
    errors: io.StringIO = io.StringIO()
    try:
        with contextlib.redirect_stderr(errors):
            found: list[Path] = find_collections(locked.parent)
    finally:
        locked.chmod(0o700)
    check(
        found == [locked] and "Can not rename" in errors.getvalue(),
        "report an old .tracker.json that can not be renamed",
    )


# Function `_test_rules_files()`:
def _test_rules_files(check: Check, directory: Path) -> None:
    """Test the rules files and the check of the `CLAUDE.md` imports.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    answers: list[str] = ["y", "y"]
    run: Callable[..., tuple[int, str]] = _runner(answers)
    original: Path = Path.cwd()
    os.chdir(directory)
    tasks: Path = directory / "TASKS" / RULES_FILE
    issues: Path = directory / "ISSUES" / RULES_FILE
    try:
        # Creating a collection writes the rules file into it.
        run("TASKS", "create")
        check(read_file(tasks) == RULES_TEXT, "a new collection's rules file")
        run("ISSUES", "create")
        check(
            read_file(issues) == RULES_TEXT,
            "the rules file is in every collection",
        )

        # A file that matches is left alone; an edited one is replaced.
        os.utime(tasks, (1_000_000, 1_000_000))
        write_file(issues, "Edited by hand.\n")
        code: int
        text: str
        code, text = run("t", "create", "1", "Fix Big Mistake")
        check(
            code == 0
            and tasks.stat().st_mtime == 1_000_000
            and read_file(issues) == RULES_TEXT,
            "the rules files are rewritten only when they differ",
        )

        # The rules files are not offered for a tag update.
        write_file(directory / "Notes.md", "See `T.fbm`.\n")
        check(
            "T.fbm" in RULES_TEXT
            and directory / "Notes.md" in tag_references(directory, "T.fbm")
            and all(
                path.name != RULES_FILE
                for path in tag_references(directory, "T.fbm")
            ),
            "the rules files are skipped when looking for a tag",
        )

        # `CLAUDE.md` imports of missing files are reported.
        write_file(
            directory / "CLAUDE.md",
            f"@TASKS/{RULES_FILE}\n@Missing.md\n@dataclass\n"
            "`@Code.md`\n@Gone/\n",
        )
        code, text = run("t", "ls")
        check(
            code == 0
            and "CLAUDE.md imports @Missing.md (line 2), which does not exist"
            in text
            and "CLAUDE.md imports @Gone/ (line 5)" in text
            and RULES_FILE not in text
            and "dataclass" not in text
            and "Code.md" not in text,
            "report a CLAUDE.md import of a missing file",
        )
        code, text = run("t", "bad")
        check(
            code == 1 and "@Missing.md" not in text,
            "CLAUDE.md is not checked when the command is not run",
        )

        # A rules file that can not be written is an error.
        issues.unlink()
        issues.mkdir()
        code, text = run("t", "ls")
        check(
            code == 1 and f"Unable to write '{issues}'" in text,
            "a rules file that can not be written",
        )
        issues.rmdir()
        answers.append("y")
        tasks.unlink()
        tasks.mkdir()
        code, text = run("NOTES", "create")
        check(
            code == 1 and "Unable to write" in text,
            "a rules file that can not be written by a new collection",
        )
    finally:
        os.chdir(original)


# Function `_test_version_control_root()`:
def _test_version_control_root(check: Check, directory: Path) -> None:
    """Test that the search for collections stops at a repository root.

    Arguments:
    * `check` (`Check`):
      Records a check: a condition that should be true and its
      description.
    * `directory` (`Path`):
      The directory to test in.
    """
    relative: str
    for relative in (
        "TASKS",
        "git_repo/.git",
        "git_repo/sub",
        "hg_repo/.hg",
        "hg_repo/ISSUES",
        "hg_repo/a/b",
        "plain/sub",
        "linked/sub",
    ):
        (directory / relative).mkdir(parents=True)
    write_file(directory / "TASKS" / COLLECTION_FILE, "{}\n")
    write_file(directory / "hg_repo" / "ISSUES" / COLLECTION_FILE, "{}\n")
    (directory / "linked" / "LINK").symlink_to(directory / "TASKS")
    check(
        find_collections(directory / "git_repo" / "sub") == [],
        "the search for collections stops at a .git root",
    )
    check(
        find_collections(directory / "hg_repo" / "a" / "b")
        == [directory / "hg_repo" / "ISSUES"],
        "collections in a version control root are found",
    )
    check(
        find_collections(directory / "plain" / "sub") == [directory / "TASKS"],
        "without version control, the search goes up",
    )
    check(
        find_collections(directory / "linked" / "sub")
        == [directory / "TASKS"],
        "a collection that is a symbolic link is skipped",
    )


if __name__ == "__main__":
    sys.exit(test())
