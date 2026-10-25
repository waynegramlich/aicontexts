#!/usr/bin/env python3
"""Check an `aicontexts` wheel as a new user would get it.

`release_check.py TARGET [VERSION]` installs `aicontexts` into a new
virtual environment, with a new home directory and nothing from the
caller's Python settings, and then runs the installed `ai_contexts
--test` and a short session with the installed `aic` (tasks and a
rule).  TARGET is where the wheel comes from:

* `source`: a wheel built from this checkout (VERSION is not used).
* `testpypi`: VERSION's wheel from test.pypi.org.  Only that one file is
  taken from test.pypi.org (its SHA-256 is checked), since anybody can
  upload there; nothing else is installed.
* `pypi`: VERSION from pypi.org.

The scratch directory (under `TMPDIR`) is removed when every check
passes, and kept, for a look, when one fails.  The exit code is 0 only
when every check passes.  `check.yml` runs this on every system.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# The package, as it is named on the indexes.
PACKAGE: str = "aicontexts"

# The JSON API of test.pypi.org, for one version of the package.
TESTPYPI_JSON: str = "https://test.pypi.org/pypi/{package}/{version}/json"

# How many times to ask test.pypi.org for a version that it may not
# list yet, and how long to wait in between.
TESTPYPI_TRIES: int = 10
TESTPYPI_WAIT_SECONDS: float = 15.0

# The environment variables that would let the caller's settings leak
# into the new user's Python.
LEAKY_PREFIXES: tuple[str, ...] = ("PIP_", "PYTHON", "VIRTUAL_ENV", "UV_")

# The source of the rule made in the session.
RULE_TEXT: str = "# Style Rules\n\nWrite short sentences.\n"


# Class `Checker`:
class Checker:
    """Run commands as a new user and keep track of the checks.

    Attributes:
    * `environment` (`dict[str, str]`): The environment of every
      command: the caller's, without its Python settings, and with a
      new home directory.
    * `failures` (`list[str]`): The descriptions of the failed checks.
    * `scratch` (`Path`): The scratch directory.
    """

    # Method `Checker.__init__()`:
    def __init__(self, scratch: Path) -> None:
        """Make the new user's home directory and environment.

        Arguments:
        * `scratch` (`Path`):
          The scratch directory.
        """
        # The new user's home directory.
        self.scratch: Path = scratch
        home: Path = scratch / "home"
        home.mkdir()

        # The caller's environment, without its Python settings.
        self.environment: dict[str, str] = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(LEAKY_PREFIXES)
        }
        self.environment.update({"HOME": str(home), "USERPROFILE": str(home)})
        self.failures: list[str] = []

    # Method `Checker.check()`:
    def check(self, condition: bool, description: str, output: str) -> None:
        """Record and print a check.

        Arguments:
        * `condition` (`bool`):
          True if the check passed.
        * `description` (`str`):
          What was checked.
        * `output` (`str`):
          What the command printed, shown when the check fails.
        """
        # Print a passed check briefly, and a failed one with output.
        if condition:
            print(f"PASS: {description}")
            return
        self.failures.append(description)
        print(f"FAIL: {description}\n{output}")

    # Method `Checker.run()`:
    def run(
        self, command: list[str], cwd: Path, answers: str = ""
    ) -> tuple[int, str]:
        """Run a command, giving it answers on its standard input.

        Arguments:
        * `command` (`list[str]`):
          The command and its arguments.
        * `cwd` (`Path`):
          The directory to run it in.
        * `answers` (`str`):
          Its standard input; with none, it reads from the null device.

        Returns:
        * (`tuple[int, str]`): The exit code, and the standard output
          and error together.
        """
        # Run it, and never wait for an answer that is not given.
        result: subprocess.CompletedProcess[str] = subprocess.run(
            command,
            cwd=cwd,
            env=self.environment,
            input=answers if answers else None,
            stdin=None if answers else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=600,
        )
        return result.returncode, result.stdout


# Function `fetch_testpypi_wheel()`:
def fetch_testpypi_wheel(version: str, directory: Path) -> Path | str:
    """Download VERSION's wheel from test.pypi.org and check its hash.

    test.pypi.org can answer 404 for a version uploaded minutes before,
    so it is asked again a few times.

    Arguments:
    * `version` (`str`):
      The version.
    * `directory` (`Path`):
      Where to put the wheel.

    Returns:
    * (`Path | str`): The wheel, or an error string.
    """
    # Ask for the version's files, waiting for it to be listed.
    url: str = TESTPYPI_JSON.format(package=PACKAGE, version=version)
    release: object = None
    attempt: int
    for attempt in range(TESTPYPI_TRIES):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                release = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code != 404 or attempt == TESTPYPI_TRIES - 1:
                return f"Unable to read '{url}': {error}"
            print(f"{url} is not listed yet; asking again")
            time.sleep(TESTPYPI_WAIT_SECONDS)
        except (OSError, ValueError) as error:
            return f"Unable to read '{url}': {error}"

    # Find the wheel among the version's files.
    files: object = release.get("urls") if isinstance(release, dict) else None
    wheels: list[dict[str, object]] = [
        file
        for file in (files if isinstance(files, list) else [])
        if isinstance(file, dict)
        and str(file.get("filename", "")).endswith(".whl")
    ]
    if len(wheels) != 1:
        return f"Expected one wheel for {PACKAGE} {version} at '{url}'"
    wheel: dict[str, object] = wheels[0]
    digests: object = wheel.get("digests")
    expected: str = (
        str(digests.get("sha256", "")) if isinstance(digests, dict) else ""
    )

    # Download it and check its hash.
    path: Path = directory / Path(str(wheel.get("filename"))).name
    try:
        with urllib.request.urlopen(
            str(wheel.get("url")), timeout=60
        ) as response:
            data: bytes = response.read()
    except OSError as error:
        return f"Unable to download '{path.name}': {error}"
    if not expected or hashlib.sha256(data).hexdigest() != expected:
        return f"'{path.name}' does not have its listed SHA-256"
    path.write_bytes(data)
    return path


# Function `install()`:
def install(checker: Checker, python: Path, target: str, version: str) -> str:
    """Install `aicontexts` into the new virtual environment.

    Arguments:
    * `checker` (`Checker`):
      Runs the commands.
    * `python` (`Path`):
      The virtual environment's Python.
    * `target` (`str`):
      "source", "testpypi" or "pypi".
    * `version` (`str`):
      The version, for "testpypi" and "pypi".

    Returns:
    * (`str`): An empty string on success, or an error string.
    """
    # Find or make the wheel, or name the release on pypi.org.
    wheels: Path = checker.scratch / "wheels"
    wheels.mkdir()
    requirement: str
    if target == "source":
        code: int
        output: str
        code, output = checker.run(
            [
                str(python),
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(wheels),
                str(Path(__file__).resolve().parent),
            ],
            checker.scratch,
        )
        if code != 0:
            return f"Unable to build the wheel:\n{output}"
        requirement = str(next(wheels.glob("*.whl")))
    elif target == "testpypi":
        wheel: Path | str = fetch_testpypi_wheel(version, wheels)
        if isinstance(wheel, str):
            return wheel
        requirement = str(wheel)
    else:
        requirement = f"{PACKAGE}=={version}"

    # Install it, with nothing else from test.pypi.org.
    code, output = checker.run(
        [str(python), "-m", "pip", "install", requirement], checker.scratch
    )
    return "" if code == 0 else f"Unable to install {requirement}:\n{output}"


# Function `session()`:
def session(checker: Checker, scripts: Path) -> None:
    """Use the installed `aic` as a new user would.

    A project (marked as the top of a git repository, so that the
    search for collections stops there) gets a TASKS collection with a
    task, and a RULES collection with an Active rule.

    Arguments:
    * `checker` (`Checker`):
      Runs the commands and records the checks.
    * `scripts` (`Path`):
      The virtual environment's directory of commands.
    """
    # Make the project and the rule's source beside it.
    project: Path = checker.scratch / "project"
    (project / ".git").mkdir(parents=True)
    sources: Path = checker.scratch / "sources"
    sources.mkdir()
    (sources / "Style_Rules.md").write_text(RULE_TEXT, encoding="utf-8")
    aic: str = shutil.which("aic", path=str(scripts)) or "aic"

    # Run each command, answering yes to each question.
    arguments: tuple[str, ...]
    answers: str
    for arguments, answers in (
        (("TASKS", "create"), "y\n"),
        (("t", "create", "1", "Write", "the", "README"), ""),
        (("t", "open", "T.wr~1"), ""),
        (("RULES", "create"), "y\n"),
        (("r", "type", "rules"), ""),
        (("r", "create", "1", "../sources/Style_Rules.md"), ""),
        (("r", "activate", "R.sr"), ""),
    ):
        code: int
        output: str
        code, output = checker.run([aic, *arguments], project, answers)
        checker.check(code == 0, f"aic {' '.join(arguments)}", output)

    # Check what the session made.
    code, output = checker.run([aic, "t", "ls"], project)
    checker.check(
        code == 0 and "Open       T.wr  Write the README" in output,
        "aic t ls shows the open task",
        output,
    )
    startup: Path = project / "TASKS" / "Startup.md"
    rule: Path = project / "RULES" / "1_Style_Rules" / "Details.md"
    active: Path = project / "RULES" / "Active_Rules.md"
    checker.check(
        startup.is_file()
        and "@1_Write_the_README/Context.md"
        in startup.read_text(encoding="utf-8"),
        "Startup.md loads the open task's context",
        "",
    )
    checker.check(
        rule.is_file()
        and rule.read_text(encoding="utf-8") == RULE_TEXT
        and active.read_text(encoding="utf-8")
        == "@1_Style_Rules/Details.md\n",
        "the Active rule's Details.md is its source, and is loaded",
        "",
    )


# Function `main()`:
def main() -> int:
    """Check `aicontexts` from the target on the command line.

    Returns:
    * (`int`): 0 if every check passed, or 1.
    """
    # Read the arguments.
    arguments: list[str] = sys.argv[1:]
    if (
        not arguments
        or arguments[0] not in ("source", "testpypi", "pypi")
        or len(arguments) != (1 if arguments[0] == "source" else 2)
    ):
        print(
            "Usage: release_check.py source | testpypi VERSION | pypi VERSION"
        )
        return 1
    target: str = arguments[0]
    version: str = arguments[1] if len(arguments) > 1 else ""

    # Make the scratch directory and the new virtual environment.
    scratch: Path = Path(tempfile.mkdtemp(prefix="release_check-"))
    where: str = f"{target} {version}".strip()
    print(f"Checking {PACKAGE} from {where} in '{scratch}'")
    checker: Checker = Checker(scratch)
    venv: Path = scratch / "venv"
    code: int
    output: str
    code, output = checker.run(
        [sys.executable, "-m", "venv", str(venv)], scratch
    )
    scripts: Path = venv / ("Scripts" if os.name == "nt" else "bin")
    python: Path = scripts / ("python.exe" if os.name == "nt" else "python")
    checker.check(code == 0, "make a virtual environment", output)

    # Install the package, then check it.
    if not checker.failures:
        error: str = install(checker, python, target, version)
        checker.check(not error, f"install {PACKAGE}", error)
    if not checker.failures:
        # Its version, when one was asked for.
        code, output = checker.run(
            [
                str(python),
                "-c",
                "import ai_contexts; print(ai_contexts.__version__)",
            ],
            scratch,
        )
        checker.check(
            code == 0 and (not version or output.strip() == version),
            f"the installed version is {version or output.strip()}",
            output,
        )

        # Its own tests, and a session with `aic`.
        ai_contexts: str = (
            shutil.which("ai_contexts", path=str(scripts)) or "ai_contexts"
        )
        code, output = checker.run([ai_contexts, "--test"], scratch)
        checker.check(
            code == 0 and " 0 failures" in output,
            "ai_contexts --test",
            output,
        )
        session(checker, scripts)

    # Report, keeping the scratch directory after a failure.
    if checker.failures:
        print(
            f"{len(checker.failures)} checks failed; the scratch directory "
            f"'{scratch}' is kept"
        )
        return 1
    shutil.rmtree(scratch, ignore_errors=True)
    print("Every check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
