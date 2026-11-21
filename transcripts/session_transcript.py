#!/usr/bin/env python3
"""Write the current Claude Code session's transcript.

Usage, run from the project (or any directory below it):

    python3 ~/public_html/projects/aicontexts/transcripts/session_transcript.py

It finds the project's
session logs in `~/.claude/projects/<project directory>/` (the
project's path with every character other than a letter or digit
turned into `-`), takes the newest log (the session being written),
and writes `~/.claude_transcripts/YYYY-MM-DD_HH:MM_PROJECT.md`
with `transcript.py`, named by the log's first time stamp (the
session's start, local time) and the project directory's name.  Run
again, it rewrites the same file.  It prints the transcript's path.
"""

import datetime
import glob
import os
import re
import subprocess
import sys

HERE: str = os.path.dirname(os.path.abspath(__file__))
OUT: str = os.path.expanduser("~/.claude_transcripts")
PROJECTS: str = os.path.expanduser("~/.claude/projects")
STAMP: re.Pattern[str] = re.compile(r'"timestamp":"([^"]+)"')


# Function `project_logs()`:
def project_logs(start: str) -> tuple[str, str]:
    """Return a project's directory and its session log directory:
    the nearest of `start` and its parents that has logs.

    Arguments:
    * `start` (`str`): Where to start looking.

    Returns:
    * (`tuple[str, str]`): The project's directory and its logs'.

    Raises:
    * `FileNotFoundError`: when no directory above `start` has logs.
    """
    directory: str = os.path.abspath(start)
    while True:
        logs: str = os.path.join(
            PROJECTS, re.sub(r"[^A-Za-z0-9]", "-", directory)
        )
        if os.path.isdir(logs):
            return directory, logs
        parent: str = os.path.dirname(directory)
        if parent == directory:
            raise FileNotFoundError(f"no session logs for {start}")
        directory = parent


# Function `started()`:
def started(log: str) -> str:
    """Return a session's start, local time, as `YYYY-MM-DD_HH:MM`.

    Arguments:
    * `log` (`str`): The session's log.

    Returns:
    * (`str`): Its first time stamp (the file's time if it has none).
    """
    with open(log, encoding="utf-8", errors="replace") as lines:
        line: str
        for line in lines:
            match: re.Match[str] | None = STAMP.search(line)
            if match is not None:
                when: datetime.datetime = datetime.datetime.fromisoformat(
                    match.group(1)
                )
                return when.astimezone().strftime("%Y-%m-%d_%H:%M")
    return datetime.datetime.fromtimestamp(os.path.getmtime(log)).strftime(
        "%Y-%m-%d_%H:%M"
    )


# Function `main()`:
def main() -> None:
    """Write the newest session's transcript and print its path."""
    # The newest log of the project around the current directory.
    project: str
    logs: str
    project, logs = project_logs(os.getcwd())
    found: list[str] = glob.glob(os.path.join(logs, "*.jsonl"))
    if not found:
        raise FileNotFoundError(f"no session logs in {logs}")
    log: str = max(found, key=os.path.getmtime)

    # The transcript, named by the session's start and the project.
    name: str = f"{started(log)}_{os.path.basename(project)}.md"
    os.makedirs(OUT, exist_ok=True)
    target: str = os.path.join(OUT, name)
    subprocess.run(
        [sys.executable, os.path.join(HERE, "transcript.py"), log, target],
        check=True,
    )
    print(target)


if __name__ == "__main__":
    main()
