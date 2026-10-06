"""The tests of tracker, run by `tracker --test`."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from tracker import (
    CLOSED_SUMMARIES,
    COLLECTION_FILE,
    DELAY_VARIABLE,
    INTERRUPT_VARIABLE,
    ITEM_FILE,
    OLD_STATUS_FILE,
    RENUMBER_FILE,
    STATES,
    SUMMARIES_VARIABLE,
    Item,
    Items,
    RenumberInterrupted,
    base_tag,
    clean_title,
    closed_time,
    has_summary,
    local_time,
    matches,
    new_metadata,
    parse_number,
    parse_priority,
    print_items,
    read_file,
    read_item,
    tag_prefix,
    tag_references,
    unique_tag,
    utc_stamp,
    write_file,
    write_item,
    write_startup,
)

# A test check: called with a condition that should be true and a description.
Check = Callable[[bool, str], None]


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
    print(f"{len(checks)} checks, {len(failures)} failures")
    return 1 if failures else 0


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
    for base, used, tag in unique_cases:
        check(unique_tag(base, used) == tag, f"unique_tag {used}")
    for level, priority in (("0", 0), ("3", 3), ("-", None)):
        check(
            parse_priority(level) == priority, f"parse_priority({level})"
        )
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
        output.getvalue()
        == "1    Pending    cde  Can Dogs Eat\n"
        "1.2  Reference  x    X\n"
        "1    Pending    0  I.cde  Can Dogs Eat\n"
        "1.2  Reference  -  I.x    X\n",
        "print_items shows the tag, and the priority if asked",
    )
    for collection_name, prefix in (
        ("TASKS", "T."), ("issues", "I."), ("2026", "2.")
    ):
        check(
            tag_prefix(collection_name) == prefix,
            f"tag_prefix({collection_name!r})",
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
        and metadata
        == {**new_metadata("Pending", item.created), "tag": "ti"}
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
    for number in ("2", "1.2", "1.1.1", "1.1.2"):
        items.create_item(number, f"item {number}")
    for number, title in (
        ("1.1", "duplicate"), ("01.1", "duplicate"),
        ("x", "bad"), ("3", "  ...!! "), ("3", ""), ("4", "gap"),
        ("1.4", "gap"), ("1.1.4", "gap"), ("3.1", "no parent"),
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


def _test_list_and_state(
    check: Check, items: Items, directory: Path
) -> None:
    """Test `list_items()`, `set_state()` and `write_startup()`."""

    def numbers(listed: list[Item] | str) -> list[str]:
        if isinstance(listed, str):  # pragma: no cover
            return [listed]
        return [item.number for item in listed]

    check(
        numbers(items.list_items())
        == ["1", "1.1", "1.1.1", "1.1.2", "1.2", "2"],
        "list all items in order",
    )
    check(
        numbers(items.list_items((1, 1)))
        == ["1.1", "1.1.1", "1.1.2"],
        "list 1.1 and its children",
    )
    check(items.list_items((9,)) == [], "list with no matches")
    check(
        numbers(items.set_state((1, 1), "Closed")) == ["1.1"],
        "close 1.1",
    )
    check(
        read_item(directory / "1.1_Fix_the_bug_now")["state"]
        == "Closed",
        "close 1.1 writes item file",
    )
    history: object = read_item(directory / "1.1_Fix_the_bug_now")[
        "history"
    ]
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


def _test_rename_delete(check: Check, directory: Path) -> None:
    """Test `rename_item()` and `delete_items()`."""
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
    for number, title in (
        ("3", "Can Dogs Eat"), ("4", "Caffeine Drink Elixir"),
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
        [item.tag for item in Items(directory).list_items((3,))]
        == ["ht2"],
        "reload a tag",
    )
    items.delete_items([(3,), (4,), (5,)])
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
        questions.append(question)
        return "y"

    result: tuple[list[Item], dict[str, Item]] | str = (
        items.delete_items([(1,)], True, yes)
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


def _test_numbering(check: Check, directory: Path) -> None:
    """Test numeric order, ranges, renumbering and fixing gaps."""
    items: Items = Items(directory)
    for part in range(1, 12):
        items.create_item(str(part), f"Top {part}")
    check(
        [item.number for item in items.list_items()][8:]
        == ["9", "10", "11"],
        "list in numeric order",
    )
    items.delete_items([(part,) for part in range(4, 12)])
    for number, title in (
        ("1.1", "B"), ("1.2", "C"), ("1.2.1", "D"), ("1.3", "E"),
        ("1.3.1", "F"), ("1.4", "G"), ("1.5", "H"),
    ):
        items.create_item(number, title)

    def tree() -> list[str]:
        return [
            f"{item.number} {item.title}"
            for item in Items(directory).list_items((1,))
        ]

    result: tuple[list[Item], dict[str, Item]] | str = (
        items.delete_items([(1, 1)])
    )
    check(
        not isinstance(result, str)
        and [item.title for item in result[0]] == ["B"]
        and {old: item.number for old, item in result[1].items()}
        == {
            "1.2": "1.1", "1.2.1": "1.1.1", "1.3": "1.2",
            "1.3.1": "1.2.1", "1.4": "1.3", "1.5": "1.4",
        }
        and tree()
        == [
            "1 Top 1", "1.1 C", "1.1.1 D", "1.2 E", "1.2.1 F", "1.3 G",
            "1.4 H",
        ]
        and read_file(directory / "1.2.1_F" / "Details.md")
        == "# 1.2.1 F\n",
        "delete 1.1 renumbers the later items and their children",
    )
    for word, message in (
        ("1.3-2", "Invalid range"), ("1.3-x", "Invalid range"),
        ("x-4", "Invalid item number"), ("1.3-9", "'1.5' does not exist"),
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


def _test_moving(check: Check, directory: Path) -> None:
    """Test creating at a place and moving."""
    items: Items = Items(directory)
    for number, title in (
        ("1", "A"), ("1.1", "B"), ("1.2", "C"), ("2", "D"), ("2.1", "E")
    ):
        items.create_item(number, title)

    def tree() -> str:
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
    for names, place, target, message in bad_moves:
        check(
            message in str(items.move_items(names, place, target)),
            f"reject move {names} {place} {target}",
        )
    check(
        items.move_items([(1, 1)], "before", (1, 2)) == {},
        "a move to the same place changes nothing",
    )


def _test_recovery(check: Check, directory: Path) -> None:
    """Test finishing a renumbering interrupted after every step."""
    directory.mkdir()
    interruptions: int = 0
    for limit in range(12):
        collection: Path = directory / f"after_{limit}"
        items: Items = Items(collection)
        # Same titles, so new directory names are old ones.
        for number, title in (
            ("1", "Notes"), ("1.1", "Child"), ("2", "Notes")
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


def _test_references(check: Check, directory: Path) -> None:
    """Test finding and updating references to a renamed tag."""
    directory.mkdir()
    items: Items = Items(directory / "TASKS")
    items.create_item("1", "Fix Big Mistake")
    text: str = "See T.fbm, T.fbm2, XT.fbm and `T.fbm`.\n"
    for relative in (
        "notes.md", "sub/deep.md", ".hidden/skipped.md", "other.txt"
    ):
        (directory / relative).parent.mkdir(exist_ok=True)
        write_file(directory / relative, text)
    (directory / "link.md").symlink_to(directory / "notes.md")
    questions: list[str] = []
    answers: list[str] = []

    def ask(question: str) -> str:
        questions.append(question)
        if not answers:
            raise EOFError
        return answers.pop(0)

    def rename(*words: str) -> str:
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
        "The following `.md` files have tags that need to be renamed:\n"
        "  notes.md\n  sub/deep.md\nNot updated; T.fbm is still used"
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
        and read_file(directory / "sub" / "deep.md") == updated
        and read_file(directory / ".hidden" / "skipped.md") == text
        and read_file(directory / "other.txt") == text,
        "update the references to a changed tag",
    )
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    (directory / "sub" / "deep.md").chmod(0o444)
    rename("Fix", "Big", "Mistake")
    check(
        tag_references(directory, "T.gf") == [directory / "notes.md"],
        "read-only files are not references",
    )
    (directory / "sub" / "deep.md").chmod(0o644)

    def refuse_writes(question: str) -> str:
        (directory / "notes.md").chmod(0o444)
        return "y"

    write_file(directory / "notes.md", "T.fbm\n")
    with contextlib.redirect_stdout(io.StringIO()):
        check(
            "Unable to update" in items.rename_command(
                ["1", "to", "Good", "Fix"], refuse_writes
            ),
            "report a reference that can not be updated",
        )


def _test_closed(check: Check, directory: Path) -> None:
    """Test `Summary.md`, `Closed.md` and Closed items in `Startup.md`."""
    directory.mkdir()
    tasks: Items = Items(directory / "TASKS")
    issues: Items = Items(directory / "ISSUES")
    for number, title in (
        ("1", "Alpha"), ("2", "Beta"), ("3", "Gamma"), ("4", "Delta")
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
    for collection, name, date in (
        (tasks, (4,), 1), (tasks, (2,), 2), (issues, (1,), 3),
        (tasks, (1,), 4),
    ):
        collection.set_state(name, "Closed")
        metadata: dict[str, object] = read_item(
            collection.directories[name]
        )
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
            == "# Older Closed Items\n\n"
            "<!-- Written by tracker; do not edit. -->\n\n"
            "These closed items are only listed by tag and title; "
            "`tracker TAG\nshow` shows the rest.\n\n- `T.d` Delta\n",
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


def _test_checks(check: Check, directory: Path) -> None:
    """Test the checks made each time a collection is loaded."""
    directory.mkdir()
    items: Items = Items(directory / "TASKS")
    for number, title in (("1", "A"), ("2", "B"), ("3", "C")):
        items.create_item(number, title)

    def load() -> tuple[Items, str]:
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
    loaded, messages = load()
    check(
        read_file(items.directories[(1,)] / "Details.md")
        == "# 1 A\nText.\n"
        and "Fixed the item number in the heading of" in messages
        and loaded.items[(1,)].title == "A",
        "fix a wrong number in a Details.md heading",
    )
    check(
        "does not start with a '# 2 TITLE' heading; `tracker T.b rename to "
        "TITLE` adds one" in messages,
        "report a Details.md without a heading",
    )
    check(
        "its directory name does not match its title 'Cee'; `tracker T.a "
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


def _test_write_failures(check: Check, directory: Path) -> None:
    """Test failing to write while renumbering or noting the time."""
    if os.geteuid() == 0:
        # Permissions are not enforced for root.
        return  # pragma: no cover
    directory.mkdir()

    def collection(name: str) -> Items:
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
        "Unable to renumber"
        in str(move.move_items([(1,)], "after", (2,))),
        "move can not renumber",
    )
    create: Items = collection("create")
    (create.directories[(1,)] / "Details.md").chmod(0o400)
    check(
        "Unable to renumber"
        in str(create.create_item("1", "N", "before")),
        "create before can not renumber",
    )


def _test_snapshot_reminder(
    check: Check, run: Callable[..., tuple[int, str]], answers: list[str]
) -> None:
    """Test the reminder to snapshot before a move or rename.

    `run` runs a command in a directory with a TASKS collection whose
    item 1 has one child, and returns its exit code and output.  The
    `answers` are given to its questions in turn.
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
            ("", ("t", "cl", "1.1"), 0, "Closed"),
            ("", ("t", "ls"), 0, "An item\n(1 Closed item not shown"),
            ("", ("t", "ls", "1.1"), 0, "Closed     T.c  Child\n"),
            ("", ("t", "ls", "-a"), 0, "Closed     T.c  Child\n"),
            ("", ("t", "cl", "1"), 0, "Closed"),
            ("", ("t", "ls", "--all", "-l"), 0, "  An item\n1.1"),
            ("", ("t", "ls"), 0, "(2 Closed items not shown;"),
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
            == f"Create tracker directory '{Path.cwd() / 'TASKS'}'? "
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
    for text, message in (
        ("{", "Unable to read"), ("[]", "not a JSON object")
    ):
        bad: Path = directory / "bad_collection"
        bad.mkdir(exist_ok=True)
        write_file(bad / COLLECTION_FILE, text)
        with contextlib.redirect_stderr(io.StringIO()):
            check(
                message in Items(bad).error,
                f"reject .tracker.json {text!r}",
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
    collection: Items = Items(read_only)
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


if __name__ == "__main__":
    sys.exit(test())
