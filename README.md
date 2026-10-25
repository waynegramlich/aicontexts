# AI Contexts: Startup Context for AI Sessions

The `ai_contexts` program manages the context that an AI loads at session
start time.  The context is broken into 3 broad categories:

* **Tasks:**
  Tasks are chunks of work, such as a feature to add or a cleanup to do.
* **Issues:**
  Issues include code bugs, feature requests, documentation, testing, etc.
  Dealing with an issue may require multiple tasks.
* **Rules:**
  Rules are instructions that an AI follows in every session, such as
  version control or coding rules, which may be shared by several projects.
  They are discussed in the section about Rules much further below.

With `ai_contexts`, you can easily switch your AI's context each time you
change your development focus, so that it loads only what is relevant.
This keeps the AI from being distracted by unrelated work and saves both time
and money.

Using `ai_contexts` is simple.  You write a few lines describing a task, and
the AI does the bookkeeping.  While the task is open, it keeps its working notes
in the task's directory, and when the task is done, it writes a short
summary and closes it.  From then on, only that summary is loaded, so a
long-running project keeps its history without the AI having to wade
through it.

## Getting Started

The installation of `ai_contexts` is covered in "Installation" near the
end of this document.

Each category is a collection of Items that lives in its own directory
(e.g. `TASKS/`, `ISSUES/` and `RULES/`).  A project can have other collections
as well (e.g. `IDEAS/`), as long as their names start with a unique letter.

These directories are manipulated by the `aic` command (which is
a symbolic link to the `ai_contexts.py` program).  For example:

* `aic TASKS create` creates the `TASKS/` directory.
* `aic ISSUES create` creates the `ISSUES/` directory.

Each one asks before creating the directory, and marks it as a collection
with a hidden `.ai_contexts.json` file inside it.  It also writes
`AI_Contexts_Rules.md` into the directory, which teaches the AI how to use
`aic`.

Next, tell the AI about them.  For Claude Code, add these two lines to
the project's `CLAUDE.md` file:

```
@TASKS/AI_Contexts_Rules.md
@TASKS/Startup.md
```

`aic` rewrites both files every time it runs, so they always exist and
are always up to date: `AI_Contexts_Rules.md` matches the version of
`aic` you have, and `TASKS/Startup.md` loads the context of your tasks
and issues.  (Every collection gets its own copy of
`AI_Contexts_Rules.md`, so you can import it from whichever collection
you have; import just one, so that it is not loaded twice.)  `aic` also
warns you about any `@` import in `CLAUDE.md` whose file does not exist.

To create a task, give it a number and a title:

```
aic TASKS create 1 Write the README
```

This creates the `TASKS/1_Write_the_README/` sub-directory.  The first
task is always number `1`, since numbers never have gaps (see below).

To see the tasks, run `aic TASKS ls`, which shows:

```
1  Pending    T.wr  Write the README
```

What you see is:

* **`1`**: This is the task number.
  (It can be hierarchical; see shortly below.)
* **`Pending`**: This is the initial task state.
* **`T.wr`**: This is the task tag.  It is constructed by taking the
  first letter of the collection name (i.e. `TASKS`) followed by a
  period.  The rest is constructed by taking the title (see next item),
  dropping the words "a", "an", "of" and "the", and concatenating the
  first letter of each remaining word in lower case.  For example,
  "Write the README" drops "the", leaving **W**rite **R**EADME, so the
  tag is `T.wr`.
* **`Write the README`**: The full title is listed last.

Collection and command names can both be shortened to any unique
prefix, in any case, so `aic t ls` works as well, and `aic t op T.wr` is
short for `aic TASKS open T.wr`.  (If a prefix is ambiguous, such as `c`
for `close` or `create`, `aic` lists the choices.)  Tags can not be
shortened, so `T.wr` must be typed in full (though `t.wr` works too).
`aic` also works from anywhere inside the project: it looks for the
collections in the current directory, and then in each parent directory
in turn, stopping at the top of a git or Mercurial repository.

Numbers are hierarchical, so a task can be broken into smaller ones:

```
aic t create 1.1 Draft the introduction
aic t create 2 Publish the README
```

Then `aic TASKS ls` lists:

```
1    Pending    T.wr  Write the README
1.1  Pending    T.di  Draft the introduction
2    Pending    T.pr  Publish the README
```

Hierarchical numbers:

* A hierarchical number is a sequence of positive integers separated by `.`
  (e.g. `1.3.2`.)
* They can be sorted, but they are never allowed to have gaps.
  Thus, task `1.3` can only be created after `1.1` and `1.2` exist.
* They change as tasks are added, moved, inserted and deleted.  This is
  why tags are typically used instead of hierarchical numbers.
* Text (and the AI) refers to a task by its tag followed by `~` and its
  number at the time, such as `T.di~1.1`, so that its directory is easy
  to find.  The number is never updated afterwards, so it records what
  the number was when the text was written.  `aic` ignores the `~1.1`,
  so `aic t open T.di~1.1` works too.

## Context Files

Each created sub-directory contains the following 4 files:

* **`Details.md`**:
  This file is entirely edited by the User.  It provides the description
  of the Task/Issue.  For a Task it describes the goal of the task.  For
  an Issue, it describes the Issue, but not necessarily how to fix it.
* **`Summary.md`**:
  This is a file where the AI stores the context it needs once the
  Task/Issue is closed.
* **`Context.md`**:
  This file is where the AI stores the context it needs when working on it.
  It is allowed to be quite detailed.  However, the AI only sees the context
  when the task or issue is in the Open (or Reference) state.
* **`.item.json`**:
  This is a hidden file entirely managed by `aic` to keep track of things.

At AI startup, the AI is directed to read at most 2 of the 3 files
above:

* **`Details.md`**: This is read until the Task/Issue is closed.
* **`Context.md`**: This is read while the Task/Issue is open.
* **`Summary.md`**: This is read once the Task/Issue is closed.

Thus, the AI gets the context it needs to focus on individual Tasks
and/or Issues.

Prior to working on a task, first enter its details into `Details.md`,
then open it:

```
aic t open T.wr
```

The next AI session loads its `Details.md` and `Context.md`.  When the
work is done, ask the AI to close the task: it writes the `Summary.md`
and it runs the `aic t close T.wr` command for you.  In practice, you rarely
run `aic` yourself once the collections exist; you ask the AI to create,
open and close tasks and issues, and it runs the commands.

## States

A task (or issue) is always in one of these states:

* **Pending:** Not started yet.  Every new task starts out Pending.
* **Open:** Being worked on.  Its `Context.md` is loaded.
* **Reference:** Not being worked on, but its `Context.md` is still
  loaded, so its notes stay available.
* **Suspended:** Put aside for now.
* **Closed:** Done.  Only its `Summary.md` is loaded.
* **Rejected:** Decided against.  It is treated like a Closed one.

The commands are named after the states (`pending`, `open`, `reference`,
`suspend`, `close` and `reject`), e.g. `aic t close T.wr`.  `aic t ls`
leaves out Closed and Rejected tasks; `aic t ls -a` lists them all.

## Moving Things Around

* `aic t move T.di after 2` moves a task (and its children), and
  `aic t create before 1 Outline the README` creates one in front of
  another; the other tasks are renumbered to make room or close the gap.
* `aic t rename T.di to Draft the overview` changes a title.  If that
  changes the tag, `ai_contexts` offers to update the `.md` files that
  use the old one, in the collections and directly in the project
  directory (it suggests a `grep` command for anywhere else).
* `aic t transfer T.di issues` moves a task that turns out to be an issue
  into `ISSUES/`, where its tag becomes `I.di`.
* `aic t delete T.di` deletes a task for good.

There is no undo, so keep the collections in a version control system.
Before a move, rename or transfer, if there has not been one for over an
hour, `ai_contexts` suggests taking a snapshot (e.g. `git commit`) first.

## Priorities

Issues can be given a priority once it is enabled for the collection
(`aic i enable priority`): 0 (catastrophic), 1 (high), 2 (medium) or 3
(low), set with `aic i priority I.dbzib 1`.  `aic i ls` then lists the
issues by priority first.

## Other Conveniences

* A tag can stand in for its collection: `aic I.dbzib close` is the same
  as `aic ISSUES close I.dbzib`.
* `aic T.wr show` shows everything about a task.
* `aic` with no arguments lists the collections, and `aic -h` lists all
  of the commands.
* Every command checks the collections and tells you about anything that
  needs fixing (such as a title edited by hand), and how to fix it.

## Rules Collections

A rules collection (e.g. `RULES/`) holds rules that the AI should load at
the start of every session, such as version control or coding rules
shared by several projects.  Each rule is a file that can live anywhere,
and `ai_contexts` keeps a read-only copy of it in the project, as the
rule's `Details.md` (the AI may not import a file from outside the
project without approval):

The easiest way to get rules is to copy them from another project:

```
aic RULES create
aic r copy ../other_project/RULES
```

A collection named `RULES` is a rules collection from the start.  (A
rules collection with another name is made with `aic NAME create`, and
then `aic n type rules` while it is still empty.)

`aic r copy` lists the other project's rules by number and title, and
asks which to copy:

```
Rules in ../other_project/RULES:
1  Code Marker Rules
2  Python Coding Rules
3  Version Control Rules
Copy which? (e.g. 1,3-5; empty for none) 2-3
1  InActive   R.pcr  Python Coding Rules
2  InActive   R.vcr  Version Control Rules
To use them: ai_contexts RULES activate 1-2
```

The choices are numbers and ranges, separated by commas or spaces, and
can also be given on the command line (`aic r copy ../other_project/RULES
2-3`).  A rule you already have is marked `(have it)` and is not copied
again.  The directory can also be any directory of rule files (e.g.
`../shared_rules/`), and a single file becomes a rule with `aic r create
1 ../shared_rules/Version_Control_Rules.md`.  Either way, the rule's file
is its source, and `aic` keeps the copy up to date with it.

`aic` refuses to make a rule from a `CLAUDE.md` file, and asks before
using a file that looks like it is about the project (like `README.md`)
or that imports other files.

A new rule is InActive until it is activated.  Every time `ai_contexts`
runs, it refreshes the copies from their source files and rewrites
`RULES/Active_Rules.md` to import the Active ones, so adding this line to
`CLAUDE.md` loads them:

```
@RULES/Active_Rules.md
```

## Installation

`ai_contexts` is a single Python program, `ai_contexts.py`, that needs
Python 3.11 or later and nothing beyond the standard library.  Nothing
else needs to be installed: the rules it gives the AI are built in.  To install
it:

1. Install the `aicontexts` package from PyPI, which gives you both the
   `ai_contexts` and `aic` commands.  With `uv` or `pipx`, it gets an
   environment of its own:

   ```
   uv tool install aicontexts
   pipx install aicontexts
   ```

   Or, without either, copy `ai_contexts.py` into a directory on your
   `PATH`, and make a symbolic link to it named `aic`:

   ```
   cp ai_contexts.py ~/bin/
   ln -s ai_contexts.py ~/bin/aic
   ```

2. Check it with `aic --test`, which runs its tests in a temporary
   directory.

3. Create the collections and set up `CLAUDE.md` as described in
   "Getting Started".

`REFERENCE.md` has the details of how `ai_contexts` works.
