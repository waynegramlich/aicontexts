#!/usr/bin/env python3
"""A simple command line task manager."""

import contextlib
import io
import os
import shutil
import string
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HELP: str = """Usage: task.py COMMAND [ARGUMENTS...]

Commands:
  create IDENTIFIER PHRASE...  Create a task (IDENTIFIER is like 1.2.3)
  rename IDENTIFIER PHRASE...  Change the phrase that names a task
  delete [-r] IDENTIFIER       Delete a task and all of its files
  list [IDENTIFIER]            List all tasks, or IDENTIFIER and its children
  ls [IDENTIFIER]              Same as list
  open [-r] IDENTIFIER         Set the task status to Open
  close [-r] IDENTIFIER        Set the task status to Closed
  suspend [-r] IDENTIFIER      Set the task status to Suspended
  test                         Run the self tests in a temporary directory

Options:
  -r, --recursive              Also apply to all of the child tasks
  help                         Print this help message

Task statuses are: Open, Suspended, Closed
New tasks are created Open."""

STATUSES: tuple[str, ...] = ("Open", "Suspended", "Closed")

# The hidden file in each task directory that holds its status.
STATUS_FILE: str = ".status"

# A test check: called with a condition that should be true and a description.
Check = Callable[[bool, str], None]


def read_file(path: Path) -> str:
    """Return the contents of the UTF-8 text file at `path`."""
    return path.read_text(encoding="utf-8")


def write_file(path: Path, text: str) -> None:
    """Write `text` to `path` as a UTF-8 text file."""
    path.write_text(text, encoding="utf-8")


def parse_identifier(identifier: str) -> tuple[int, ...] | str:
    """Convert an identifier like "1.2.3" into a name like (1, 2, 3).

    Returns the name, or an error string if the identifier is invalid.
    """
    if not identifier:
        return "Task identifier is empty"
    name_list: list[int] = []
    for part in identifier.split("."):
        if not part.isdecimal() or int(part) <= 0:
            return (
                f"Invalid task identifier '{identifier}': it must be "
                "positive integers separated by periods (e.g. 1, 2.3, "
                "or 1.2.3)"
            )
        name_list.append(int(part))
    return tuple(name_list)


def clean_phrase(phrase: str) -> str:
    """Return `phrase` cleaned up for use in a task directory name.

    Hyphens and underscores separate words, periods are kept, other
    punctuation is removed, a word with no letters or digits is dropped,
    the first word is capitalized and the words are joined by
    underscores.  The result can be pasted into a shell command without
    quoting.  Returns an empty string if `phrase` has no words.
    """
    remove: str = (
        string.punctuation.replace("-", "").replace("_", "").replace(".", "")
    )
    words: list[str] = [
        word
        for word in phrase.translate(str.maketrans("-_", "  ", remove)).split()
        if any(character.isalnum() for character in word)
    ]
    if not words:
        return ""
    words[0] = words[0][0].upper() + words[0][1:]
    return "_".join(words)


def parse_recursive(
    command: str, arguments: list[str]
) -> tuple[tuple[int, ...], bool] | str:
    """Parse the `[-r] IDENTIFIER` arguments of `command`.

    Returns the task name and whether `-r` was given, or an error string.
    """
    recursive: bool = False
    identifiers: list[str] = []
    for argument in arguments:
        if argument in ("-r", "--recursive"):
            recursive = True
        else:
            identifiers.append(argument)
    if len(identifiers) != 1:
        return f"Usage: task.py {command} [-r] IDENTIFIER"
    name: tuple[int, ...] | str = parse_identifier(identifiers[0])
    if isinstance(name, str):
        return name
    return name, recursive


@dataclass
class Task:
    """A single task."""

    name: tuple[int, ...]
    phrase: str
    status: str = "Open"

    def __post_init__(self) -> None:
        """Ensure that the name and status are valid.

        The name must be a non-empty tuple of positive integers and the
        status must be one of `STATUSES`.  Raises a `ValueError` if not.
        """
        if not (
            isinstance(self.name, tuple)
            and self.name
            and all(
                isinstance(number, int)
                and not isinstance(number, bool)
                and number > 0
                for number in self.name
            )
        ):
            raise ValueError(
                f"Task name {self.name!r} is not a non-empty tuple of "
                "positive integers"
            )
        if self.status not in STATUSES:
            raise ValueError(
                f"Task status {self.status!r} is not one of "
                f"{', '.join(STATUSES)}"
            )

    @property
    def identifier(self) -> str:
        """Return the name as period separated numbers, like "1.2.3"."""
        return ".".join(str(number) for number in self.name)


class Tasks:
    """A collection of tasks."""

    def __init__(self, tasks_directory: Path = Path("TASKS")) -> None:
        """Initialize a Tasks collection.

        Creates `tasks_directory` (by default "TASKS" in the current
        directory) if it is not already present.  If the directory can
        not be created or is not writable, an error is printed to stderr
        and `self.error` is set to a non-empty error string.
        """
        self.tasks_directory: Path = tasks_directory
        self.tasks: dict[tuple[int, ...], Task] = {}
        self.directories: dict[tuple[int, ...], Path] = {}
        self.error: str = ""
        try:
            tasks_directory.mkdir(exist_ok=True)
        except OSError as error:
            self.error = (
                f"Unable to create directory '{tasks_directory}': {error}"
            )
        else:
            if not os.access(tasks_directory, os.W_OK):
                self.error = (
                    f"No write access to directory '{tasks_directory}'"
                )
        if self.error:
            print(self.error, file=sys.stderr)
        else:
            self.load_tasks()

    def load_tasks(self) -> None:
        """Load the existing tasks from the task directories.

        A directory that is not a valid task directory is skipped with a
        warning printed to stderr.
        """
        for task_directory in sorted(self.tasks_directory.iterdir()):
            if not task_directory.is_dir():
                continue
            identifier, _, cleaned_phrase = task_directory.name.partition("_")
            name: tuple[int, ...] | str = parse_identifier(identifier)
            if isinstance(name, str):
                print(f"Skipping '{task_directory}': {name}", file=sys.stderr)
                continue
            phrase: str = cleaned_phrase.replace("_", " ")
            try:
                status: str = read_file(task_directory / STATUS_FILE).strip()
                details: str = read_file(task_directory / "Details.md")
                heading: str = details.partition("\n")[0]
            except OSError as error:
                print(f"Skipping '{task_directory}': {error}", file=sys.stderr)
                continue
            prefix: str = f"# {identifier} "
            if heading.startswith(prefix):
                phrase = heading[len(prefix):].strip()
            try:
                self.tasks[name] = Task(name, phrase, status)
            except ValueError as error:
                print(f"Skipping '{task_directory}': {error}", file=sys.stderr)
            else:
                self.directories[name] = task_directory

    def list_tasks(self, name: tuple[int, ...] = ()) -> list[Task]:
        """Return the tasks starting with `name`, sorted by name.

        An empty `name` returns all of the tasks.
        """
        return [
            self.tasks[task_name]
            for task_name in sorted(self.tasks)
            if task_name[: len(name)] == name
        ]

    def create_task(self, identifier: str, phrase: str) -> Task | str:
        """Create a new Task.

        Returns the new Task, or an error string if it can not be created.
        """
        name: tuple[int, ...] | str = parse_identifier(identifier)
        if isinstance(name, str):
            return name
        identifier = ".".join(str(number) for number in name)
        sub_directories: set[str] = {
            path.name.split("_", 1)[0]
            for path in self.tasks_directory.iterdir()
            if path.is_dir()
        }
        if name in self.tasks or identifier in sub_directories:
            return f"Task '{identifier}' already exists"
        phrase = phrase.strip()
        cleaned_phrase: str = clean_phrase(phrase)
        if not cleaned_phrase:
            return f"Task '{identifier}' has an empty phrase"
        task_directory: Path = (
            self.tasks_directory / f"{identifier}_{cleaned_phrase}"
        )
        task: Task = Task(name, phrase)
        try:
            task_directory.mkdir()
            write_file(task_directory / STATUS_FILE, f"{task.status}\n")
            write_file(
                task_directory / "Context.md", "# LLM Agent Context Log\n"
            )
            write_file(
                task_directory / "Details.md", f"# {identifier} {phrase}\n"
            )
        except OSError as error:
            return (
                f"Unable to create task directory '{task_directory}': {error}"
            )
        self.tasks[name] = task
        self.directories[name] = task_directory
        return task

    def select_tasks(
        self, name: tuple[int, ...], recursive: bool = False
    ) -> list[Task] | str:
        """Return task `name`, and its children if `recursive`.

        Returns an error string if no task matches.
        """
        identifier: str = ".".join(str(number) for number in name)
        if recursive:
            selected: list[Task] = self.list_tasks(name)
            if not selected:
                return f"No tasks match '{identifier}'"
            return selected
        if name in self.tasks:
            return [self.tasks[name]]
        return f"Task '{identifier}' does not exist"

    def rename_task(self, name: tuple[int, ...], phrase: str) -> Task | str:
        """Change the phrase of task `name`.

        The task directory is renamed to match, and the heading line of its
        `Details.md` is rewritten, or added if it is missing.  Returns the
        renamed task, or an error string if it can not be renamed.
        """
        identifier: str = ".".join(str(number) for number in name)
        if name not in self.tasks:
            return f"Task '{identifier}' does not exist"
        phrase = phrase.strip()
        cleaned_phrase: str = clean_phrase(phrase)
        if not cleaned_phrase:
            return f"Task '{identifier}' has an empty phrase"
        old_directory: Path = self.directories[name]
        new_directory: Path = (
            self.tasks_directory / f"{identifier}_{cleaned_phrase}"
        )
        if new_directory != old_directory and new_directory.exists():
            return f"'{new_directory}' already exists"
        details_path: Path = old_directory / "Details.md"
        try:
            details: str = read_file(details_path)
            heading, _, rest = details.partition("\n")
            if not heading.startswith(f"# {identifier} "):
                rest = details
            write_file(details_path, f"# {identifier} {phrase}\n{rest}")
            old_directory.rename(new_directory)
        except OSError as error:
            return f"Unable to rename task '{identifier}': {error}"
        task: Task = self.tasks[name]
        task.phrase = phrase
        self.directories[name] = new_directory
        return task

    def delete_task(
        self, name: tuple[int, ...], recursive: bool = False
    ) -> list[Task] | str:
        """Delete task `name`, and its children if `recursive`.

        Each task directory is removed along with everything in it.
        Returns the deleted tasks, or an error string on failure.
        """
        selected: list[Task] | str = self.select_tasks(name, recursive)
        if isinstance(selected, str):
            return selected
        for task in selected:
            task_directory: Path = self.directories[task.name]
            try:
                shutil.rmtree(task_directory)
            except OSError as error:
                return f"Unable to delete '{task_directory}': {error}"
            del self.tasks[task.name]
            del self.directories[task.name]
        return selected

    def set_status(
        self, name: tuple[int, ...], status: str, recursive: bool = False
    ) -> list[Task] | str:
        """Set the status of task `name`, and its children if `recursive`.

        Returns the changed tasks, or an error string on failure.
        """
        if status not in STATUSES:
            return f"Status '{status}' is not one of {', '.join(STATUSES)}"
        changed: list[Task] | str = self.select_tasks(name, recursive)
        if isinstance(changed, str):
            return changed
        for task in changed:
            status_path: Path = self.directories[task.name] / STATUS_FILE
            try:
                write_file(status_path, f"{status}\n")
            except OSError as error:
                return f"Unable to write '{status_path}': {error}"
            task.status = status
        return changed

    def write_startup(self) -> str:
        """Write `Startup` into the tasks directory.

        Every line is an `@` import: the `Details.md` of every task, and
        the `Context.md` of every Open task, so that adding
        `@TASKS/Startup` to `CLAUDE.md` loads them.
        Returns an empty string on success, or an error string on failure.
        """
        lines: list[str] = []
        for task in self.list_tasks():
            task_directory: Path = self.directories[task.name]
            file_names: tuple[str, ...] = ("Details.md",)
            if task.status == "Open":
                file_names += ("Context.md",)
            for file_name in file_names:
                if (task_directory / file_name).is_file():
                    lines.append(f"@{task_directory.name}/{file_name}")
        startup_path: Path = self.tasks_directory / "Startup"
        try:
            write_file(startup_path, "".join(f"{line}\n" for line in lines))
        except OSError as error:
            return f"Unable to write '{startup_path}': {error}"
        return ""

    def create_command(self, arguments: list[str]) -> str:
        """Run `create IDENTIFIER PHRASE...`.

        Returns an empty string on success, or an error string on failure.
        """
        if len(arguments) < 2:
            return "Usage: task.py create IDENTIFIER PHRASE..."
        result: Task | str = self.create_task(
            arguments[0], " ".join(arguments[1:])
        )
        return result if isinstance(result, str) else ""

    def list_command(self, arguments: list[str]) -> str:
        """Run `list [IDENTIFIER]`.

        Returns an empty string on success, or an error string on failure.
        """
        if len(arguments) > 1:
            return "Usage: task.py list [IDENTIFIER]"
        name: tuple[int, ...] | str = (
            parse_identifier(arguments[0]) if arguments else ()
        )
        if isinstance(name, str):
            return name
        print_tasks(self.list_tasks(name))
        return ""

    def status_command(self, command: str, arguments: list[str]) -> str:
        """Run `open`, `close` or `suspend` with `[-r] IDENTIFIER`.

        Returns an empty string on success, or an error string on failure.
        """
        parsed: tuple[tuple[int, ...], bool] | str = parse_recursive(
            command, arguments
        )
        if isinstance(parsed, str):
            return parsed
        name, recursive = parsed
        status: str = {
            "open": "Open", "close": "Closed", "suspend": "Suspended"
        }[command]
        changed: list[Task] | str = self.set_status(name, status, recursive)
        if isinstance(changed, str):
            return changed
        print_tasks(changed)
        return ""

    def rename_command(self, arguments: list[str]) -> str:
        """Run `rename IDENTIFIER PHRASE...`.

        Returns an empty string on success, or an error string on failure.
        """
        if len(arguments) < 2:
            return "Usage: task.py rename IDENTIFIER PHRASE..."
        name: tuple[int, ...] | str = parse_identifier(arguments[0])
        if isinstance(name, str):
            return name
        renamed: Task | str = self.rename_task(name, " ".join(arguments[1:]))
        if isinstance(renamed, str):
            return renamed
        print_tasks([renamed])
        return ""

    def delete_command(self, arguments: list[str]) -> str:
        """Run `delete [-r] IDENTIFIER`.

        Returns an empty string on success, or an error string on failure.
        """
        parsed: tuple[tuple[int, ...], bool] | str = parse_recursive(
            "delete", arguments
        )
        if isinstance(parsed, str):
            return parsed
        deleted: list[Task] | str = self.delete_task(*parsed)
        if isinstance(deleted, str):
            return deleted
        print_tasks(deleted)
        return ""

    @staticmethod
    def test() -> int:
        """Test the task manager in a temporary directory.

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
            Tasks._test_parsing(check)
            Tasks._test_tasks(check, root / "TASKS")
            Tasks._test_reload(check, root / "TASKS")
            Tasks._test_rename_delete(check, root / "rename_delete")
            Tasks._test_commands(check, root / "commands")
            Tasks._test_errors(check, root / "errors")
        print(f"{len(checks)} checks, {len(failures)} failures")
        return 1 if failures else 0

    @staticmethod
    def _test_parsing(check: Check) -> None:
        """Test `parse_identifier()` and `Task` validation."""
        check(parse_identifier("1.2.3") == (1, 2, 3), "parse 1.2.3")
        check(parse_identifier("01.2") == (1, 2), "parse 01.2")
        for identifier in ("", "0", "-1", "1..2", "1.2.", "a.b", "1.0"):
            check(
                isinstance(parse_identifier(identifier), str),
                f"reject identifier {identifier!r}",
            )
        for phrase, cleaned in (
            ("fix the-bug, (now)!", "Fix_the_bug_now"),
            ("`README.md` documentation", "README.md_documentation"),
            ("`.pth` files", ".pth_files"),
            ("task 1.2.3", "Task_1.2.3"),
            ("say $HOME's `ls` & <more>; ok?", "Say_HOMEs_ls_more_ok"),
            ("  ... !! ", ""),
        ):
            check(
                clean_phrase(phrase) == cleaned,
                f"clean_phrase({phrase!r})",
            )
        check(Task((1, 2), "p").identifier == "1.2", "Task.identifier")
        check(Task((1,), "p").status == "Open", "default status is Open")
        for status in STATUSES:
            check(Task((1,), "p", status).status == status, f"{status} ok")
        bad_tasks: list[tuple[object, str]] = [
            ((), "Open"), ((0,), "Open"), ((True,), "Open"),
            ((1, "2"), "Open"), ([1], "Open"), ((1,), "Done"),
        ]
        for name, status in bad_tasks:
            try:
                Task(name, "p", status)  # type: ignore[arg-type]
            except ValueError:
                check(True, f"reject Task({name!r}, {status!r})")
            else:  # pragma: no cover
                check(False, f"reject Task({name!r}, {status!r})")

    @staticmethod
    def _test_tasks(check: Check, directory: Path) -> None:
        """Test creating, listing and changing the status of tasks."""
        tasks: Tasks = Tasks(directory)
        check(not tasks.error and directory.is_dir(), "create TASKS")
        task: Task | str = tasks.create_task("1", "  top task  ")
        check(
            isinstance(task, Task) and task.phrase == "top task",
            "create task 1",
        )
        top: Path = directory / "1_Top_task"
        check(read_file(top / STATUS_FILE) == "Open\n", "status file")
        check(
            read_file(top / "Context.md") == "# LLM Agent Context Log\n",
            "Context.md file",
        )
        check(
            read_file(top / "Details.md") == "# 1 top task\n",
            "Details.md file",
        )
        tasks.create_task("1.2", "fix the-bug, (now)!")
        check(
            (directory / "1.2_Fix_the_bug_now").is_dir(),
            "directory name is cleaned up",
        )
        # Created out of order to test that listing sorts numerically.
        for identifier in ("2", "1.20", "1.2.10", "1.2.3"):
            tasks.create_task(identifier, f"task {identifier}")
        for identifier, phrase in (
            ("1.2", "duplicate"), ("01.2", "duplicate"),
            ("x", "bad"), ("3", "  ...!! "), ("4", ""),
        ):
            check(
                isinstance(tasks.create_task(identifier, phrase), str),
                f"reject create {identifier!r} {phrase!r}",
            )
        check(
            not any(directory.glob("3_*")) and not any(directory.glob("4_*")),
            "rejected tasks have no directory",
        )
        Tasks._test_list_and_status(check, tasks, directory)

    @staticmethod
    def _test_list_and_status(
        check: Check, tasks: "Tasks", directory: Path
    ) -> None:
        """Test `list_tasks()`, `set_status()` and `write_startup()`."""

        def identifiers(listed: list[Task] | str) -> list[str]:
            if isinstance(listed, str):  # pragma: no cover
                return [listed]
            return [task.identifier for task in listed]

        check(
            identifiers(tasks.list_tasks())
            == ["1", "1.2", "1.2.3", "1.2.10", "1.20", "2"],
            "list all tasks in numeric order",
        )
        check(
            identifiers(tasks.list_tasks((1, 2)))
            == ["1.2", "1.2.3", "1.2.10"],
            "list 1.2 and its children",
        )
        check(tasks.list_tasks((9,)) == [], "list with no matches")
        check(
            identifiers(tasks.set_status((1, 2), "Closed")) == ["1.2"],
            "close 1.2",
        )
        check(
            read_file(directory / "1.2_Fix_the_bug_now" / STATUS_FILE)
            == "Closed\n",
            "close 1.2 writes status file",
        )
        check(tasks.tasks[(1, 2, 3)].status == "Open", "1.2.3 still Open")
        check(
            identifiers(tasks.set_status((1, 2), "Suspended", True))
            == ["1.2", "1.2.3", "1.2.10"],
            "suspend -r 1.2",
        )
        check(tasks.tasks[(1, 20)].status == "Open", "1.20 still Open")
        for name, status, recursive in (
            ((9,), "Closed", False), ((9,), "Closed", True),
            ((1,), "Done", False),
        ):
            check(
                isinstance(tasks.set_status(name, status, recursive), str),
                f"reject set_status {name} {status} {recursive}",
            )
        check(tasks.write_startup() == "", "write Startup")
        check(
            read_file(directory / "Startup")
            == "@1_Top_task/Details.md\n@1_Top_task/Context.md\n"
            "@1.2_Fix_the_bug_now/Details.md\n"
            "@1.2.3_Task_1.2.3/Details.md\n"
            "@1.2.10_Task_1.2.10/Details.md\n"
            "@1.20_Task_1.20/Details.md\n@1.20_Task_1.20/Context.md\n"
            "@2_Task_2/Details.md\n@2_Task_2/Context.md\n",
            "Startup contents",
        )

    @staticmethod
    def _test_reload(check: Check, directory: Path) -> None:
        """Test loading tasks back from disk, including bad directories."""
        (directory / "junk").mkdir()
        bad_status: Path = directory / "5_Bad_status"
        bad_status.mkdir()
        write_file(bad_status / STATUS_FILE, "Done\n")
        write_file(bad_status / "Details.md", "# 5 Bad status\n")
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            tasks: Tasks = Tasks(directory)
        check(errors.getvalue().count("Skipping") == 2, "skip bad tasks")
        check(len(tasks.tasks) == 6, "reload 6 tasks")
        check(
            tasks.tasks[(1, 2)].phrase == "fix the-bug, (now)!",
            "reload phrase from Details.md",
        )
        check(
            [task.status for task in tasks.list_tasks((1,))]
            == ["Open", "Suspended", "Suspended", "Suspended", "Open"],
            "reload statuses",
        )
        not_a_directory: Path = directory.parent / "not_a_directory"
        write_file(not_a_directory, "")
        with contextlib.redirect_stderr(io.StringIO()):
            check(bool(Tasks(not_a_directory).error), "TASKS is a file")

    @staticmethod
    def _test_rename_delete(check: Check, directory: Path) -> None:
        """Test `rename_task()` and `delete_task()`."""
        tasks: Tasks = Tasks(directory)
        for identifier, phrase in (
            ("1", "One"), ("1.1", "Child"), ("2", "Two")
        ):
            tasks.create_task(identifier, phrase)
        renamed: Task | str = tasks.rename_task((1,), " Uno, again ")
        check(
            isinstance(renamed, Task) and renamed.phrase == "Uno, again",
            "rename 1",
        )
        check(
            (directory / "1_Uno_again").is_dir()
            and not (directory / "1_One").exists(),
            "rename moves the task directory",
        )
        check(
            read_file(directory / "1_Uno_again" / "Details.md")
            == "# 1 Uno, again\n",
            "rename rewrites the Details.md heading",
        )
        write_file(directory / "2_Two" / "Details.md", "Notes\n")
        tasks.rename_task((2,), "Two")
        check(
            read_file(directory / "2_Two" / "Details.md")
            == "# 2 Two\nNotes\n",
            "rename adds a missing Details.md heading",
        )
        (directory / "2_Taken").mkdir()
        for name, phrase in (((9,), "Nine"), ((1,), " !! "), ((2,), "taken")):
            check(
                isinstance(tasks.rename_task(name, phrase), str),
                f"reject rename {name} {phrase!r}",
            )
        (directory / "2_Taken").rmdir()
        check(
            Tasks(directory).tasks[(1,)].phrase == "Uno, again",
            "reload a renamed task",
        )
        deleted: list[Task] | str = tasks.delete_task((1,))
        check(
            not isinstance(deleted, str)
            and [task.identifier for task in deleted] == ["1"]
            and not (directory / "1_Uno_again").exists()
            and (directory / "1.1_Child").is_dir(),
            "delete 1 keeps 1.1",
        )
        tasks.create_task("1", "One")
        deleted = tasks.delete_task((1,), True)
        check(
            not isinstance(deleted, str)
            and [task.identifier for task in deleted] == ["1", "1.1"]
            and not any(directory.glob("1*")),
            "delete -r 1",
        )
        for recursive in (False, True):
            check(
                isinstance(tasks.delete_task((9,), recursive), str),
                f"reject delete 9 recursive={recursive}",
            )
        details_path: Path = directory / "2_Two" / "Details.md"
        details_path.unlink()
        details_path.mkdir()
        check(
            "Unable to rename" in str(tasks.rename_task((2,), "Deux")),
            "rename failure",
        )
        if os.geteuid() == 0:
            # Permissions are not enforced for root.
            return  # pragma: no cover
        directory.chmod(0o500)
        try:
            check(
                "Unable to delete" in str(tasks.delete_task((2,))),
                "delete failure",
            )
        finally:
            directory.chmod(0o700)

    @staticmethod
    def _test_commands(check: Check, directory: Path) -> None:
        """Test `run_command()` from inside `directory`."""

        def run(*arguments: str) -> tuple[int, str]:
            output: io.StringIO = io.StringIO()
            with (
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(output),
            ):
                code: int = Tasks.run_command(list(arguments))
            return code, output.getvalue()

        directory.mkdir()
        original: Path = Path.cwd()
        os.chdir(directory)
        try:
            for arguments, code, text in (
                ((), 0, "Usage"),
                (("help",), 0, "Usage"),
                (("create", "1", "A", "task"), 0, ""),
                (("create", "1.1", "Child"), 0, ""),
                (("create", "1"), 1, "Usage"),
                (("create", "1", "again"), 1, "already exists"),
                (("ls",), 0, "A task"),
                (("list", "1.1"), 0, "Child"),
                (("ls", "x"), 1, "Invalid"),
                (("ls", "1", "2"), 1, "Usage"),
                (("close", "1"), 0, "Closed"),
                (("suspend", "--recursive", "1"), 0, "1.1"),
                (("open", "-r", "1"), 0, "Open"),
                (("open",), 1, "Usage"),
                (("close", "9"), 1, "does not exist"),
                (("close", "x"), 1, "Invalid"),
                (("rename", "1.1", "New", "child"), 0, "New child"),
                (("rename", "1"), 1, "Usage"),
                (("rename", "x", "y"), 1, "Invalid"),
                (("rename", "9", "Nine"), 1, "does not exist"),
                (("create", "2", "Doomed"), 0, ""),
                (("delete", "2"), 0, "Doomed"),
                (("delete",), 1, "Usage"),
                (("delete", "x"), 1, "Invalid"),
                (("delete", "-r", "9"), 1, "No tasks match"),
                (("bogus",), 1, "Unknown command"),
            ):
                result: tuple[int, str] = run(*arguments)
                check(
                    result[0] == code and text in result[1],
                    f"command {' '.join(arguments)!r}",
                )
            check(
                "@1_A_task/Details.md"
                in read_file(Path("TASKS/Startup")),
                "commands write Startup",
            )
            (directory / "file").mkdir()
            os.chdir(directory / "file")
            write_file(Path("TASKS"), "")
            code, text = run("ls")
            check(
                code == 1 and "Unable to create" in text,
                "command with TASKS as a file",
            )
        finally:
            os.chdir(original)

    @staticmethod
    def _test_errors(check: Check, directory: Path) -> None:
        """Test the error paths for files that can not be read or written."""
        directory.mkdir()
        tasks: Tasks = Tasks(directory / "TASKS")
        tasks.create_task("1", "One")
        no_status: Path = directory / "TASKS" / "2_No_status"
        no_status.mkdir()
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            tasks = Tasks(directory / "TASKS")
        check("2_No_status" in errors.getvalue(), "skip missing status file")
        status_path: Path = directory / "TASKS" / "1_One" / STATUS_FILE
        status_path.unlink()
        status_path.mkdir()
        check(
            "Unable to write" in str(tasks.set_status((1,), "Closed")),
            "set_status write failure",
        )
        (directory / "TASKS" / "Startup").mkdir()
        check(
            "Unable to write" in tasks.write_startup(),
            "write_startup failure",
        )
        if os.geteuid() == 0:
            # Permissions are not enforced for root.
            return  # pragma: no cover
        read_only: Path = directory / "read_only"
        read_only.mkdir(mode=0o500)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                tasks = Tasks(read_only)
            check("No write access" in tasks.error, "read-only TASKS")
            check(
                "Unable to create" in str(tasks.create_task("1", "One")),
                "create_task in read-only TASKS",
            )
        finally:
            read_only.chmod(0o700)

    @staticmethod
    def run_command(arguments: list[str]) -> int:
        """Run a task manager command.

        Returns 0 for success and 1 for failure.
        """
        if not arguments:
            print(HELP)
            return 0
        if arguments == ["test"]:
            return Tasks.test()
        tasks: Tasks = Tasks()
        if tasks.error:
            return 1
        command: str = arguments[0]
        error: str = ""
        match command:
            case "help" | "-h" | "--help":
                print(HELP)
            case "create":
                error = tasks.create_command(arguments[1:])
            case "list" | "ls":
                error = tasks.list_command(arguments[1:])
            case "open" | "close" | "suspend":
                error = tasks.status_command(command, arguments[1:])
            case "rename":
                error = tasks.rename_command(arguments[1:])
            case "delete":
                error = tasks.delete_command(arguments[1:])
            case _:
                error = f"Unknown command '{command}'\n{HELP}"
        if not error:
            error = tasks.write_startup()
        if error:
            print(error, file=sys.stderr)
            return 1
        return 0


def print_tasks(tasks: list[Task]) -> None:
    """Print one line per task with its identifier, status and phrase."""
    width: int = max((len(task.identifier) for task in tasks), default=0)
    status_width: int = max(len(status) for status in STATUSES)
    for task in tasks:
        print(
            f"{task.identifier:<{width}}  "
            f"{task.status:<{status_width}}  {task.phrase}"
        )


def main() -> None:
    """Run the task manager."""
    sys.exit(Tasks.run_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
