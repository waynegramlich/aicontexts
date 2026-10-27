# LLM Agent Context Log

## Progress (2026-10-25)

* Checks (`R.gsr` steps 1-3): `gh` signed in as `waynegramlich`
  (scopes `repo`, `workflow`, ...); no `aicontexts` on GitHub and no
  git remote; the only symbolic links (`ai_contexts`, `aic`) point at
  `ai_contexts.py`; no secrets in the history (28 commits, one author).
* The user chose public, HTTPS and tracking this as `T.pcbtg`.
* `gh config set git_protocol https` left the per-host protocol at ssh,
  so `gh repo create` made an ssh remote; fixed with `gh config set -h
  github.com git_protocol https` and `git remote set-url`.  `gh auth
  setup-git` is done.
* Created https://github.com/waynegramlich/aicontexts (public, remote
  `github`, HTTPS).  Nothing pushed yet.
* `rule_sources/GitHub_Setup_Rules.md`: added the per-host protocol
  trap, the public author email, and split pushing into its own step.

* Added `git_hooks/` (copied from `../ezpkg`, trailer `Assisted-by:
  Claude Code:claude-opus-5-5`) and `git config core.hooksPath
  git_hooks`; tested in a scratch repository (trailer added, an
  empty message refused).
* The user: no push until `ISSUES/` is empty (it is, as of
  2026-10-25).

## Next

* Push `main` (the user's go), verify with `git ls-remote`.
* Then `R.gwr`: `check.yml`, `release.yml`, PyPI.

## Upstream (2026-10-25)

* The user pushes with a plain `git push`: `branch.main.remote github`
  and `branch.main.merge refs/heads/main` set by `git config`
  (`--set-upstream-to` needs `github/main` to exist); `git push
  --dry-run` showed `* [new branch] main -> main`.  Added to `R.gsr`
  step 5.
* The user pushed `e665ae4`; verified: `git ls-remote github` matches
  `git rev-parse main`, `defaultBranchRef` is `main`, the `ai_contexts`
  and `aic` links are mode 120000 and `ai_contexts.py` and the hooks
  100755.  `e665ae4` and `d7703d3` carry the `Assisted-by:` trailer.

## `TAG~NUMBER` references (2026-10-25, a side request)

* Text and commit messages refer to items as `T.pcbtg~12`: the number
  when written, never updated (it is history, only a help in finding
  `Details.md`).  `Items.resolve()` checks and ignores the `~NUMBER`;
  `tag_pattern()` already let a rename keep it.  `RULES_TEXT`, `HELP`,
  `README.md`, `REFERENCE.md` and the tests were updated (552 checks).
* A transfer drops the old `~NUMBER` (`T.fbm~12` becomes `I.fbm`):
  `update_references(drop_numbers=True)`.  Commit messages keep
  `~NUMBER` (the user: right for a checkout of that commit).
* The user pushed `6101e84` (the `~NUMBER` work); verified with `git ls-remote`.

## `pylint` (2026-10-25, a side request)

* `R.pcr` now says to rerun `ruff`, `mypy --strict` and `pylint` after
  every change, and how to turn off deliberate `pylint` messages.
* `pylint` 4.1.3 from `uv tool install pylint` (`~/.local/bin`, ahead of
  Ubuntu's 3.0.3); `check.yml` should pin `pylint==4.1.3`.
* Both files rate 10.00/10: size limits off by module-level comments,
  `_question` for an unused argument, keyword-only arguments plus a
  `def`-line disable in `_test_interrupted_transfer()`, and a
  `disable-next` for the `--test` import (`import-outside-toplevel`,
  `cyclic-import`).
* `uv tool install` also gave ruff 0.17.2, mypy 2.4.0 and flake8 7.4.1
  (were 0.17.1, 1.9.0, 7.0.0); all four checkers are clean.  `R.pcr`
  now has a "Checkers" section (all four, and quieting each by name).
* Added and activated `R.gar` (General AI Rules; was `R.gar2`, then
  `R.gr`; `rule_sources/General_AI_Rules.md`): number lists the user
  answers.
* `R.gar` also says: refer to code as `FILE:FIRST-LAST`, and check for
  out of date tools at session start (`uv tool list --outdated`,
  `uv self update --dry-run`, `gh release view --repo cli/cli`).  On
  2026-10-25: `uv` 0.12.21 (0.13.5 current), `gh` 2.100.0 (2.103.2).

## Rules layout (2026-10-25, the user's #9)

* A rule's directory now holds only `Details.md` (the read-only copy of
  its source, with the source's own heading) and `.item.json` (which
  now has the title).  `copy_path()` is `Details.md`; `create_item()` and
  `rename_item()` keep a rule's title in `.item.json`; `check_items()`
  skips a rule's heading; `do_renumber()` and `do_transfer()` leave a
  rules collection's `Details.md` alone (by `type_name()`);
  `upgrade_rule()` moves the old layout on load.  New tests in
  `_test_types()`, `_test_rule_failures()` and `_test_rule_moves()`
  (566 checks; the move/transfer tests fail without the fix).  This
  project's six rules were moved on the next run.
* The user chose to retitle GitHub Actions Rules to GitHub Workflow
  Rules (`R.gwr`), so that General AI Rules (file
  `General_AI_Rules.md`) could be `R.gar`.
* Its source became `rule_sources/GitHub_Workflow_Rules.md` (heading
  `# GitHub Workflow Rules`), and `R.gsr`'s two mentions of the file
  were updated.
* Emacs lock files (`.#*`): not in `.gitignore`; the user wants to be
  told when one turns up.

## Packaging and workflows (2026-10-25)

* The user: nothing goes to pypi.org or test.pypi.org until they say
  so; do everything up to the GitHub/PyPI web pages.  `../ezpkg` and
  `../solidcraft` use aicontexts and must keep working.
* Scratch copies of both (collections, top `.md` files, rule sources)
  convert cleanly with the new code; `Startup.md` unchanged.  Found:
  `ezpkg`'s rule 5 source `../aicontexts/rule_sources/GitHub_Actions_
  Rules.md` is gone (renamed); `solidcraft`'s `ai_contexts` link points
  at `../ai_contexts/ai_contexts.py`, which no longer exists.
* Added `__version__ = "0.1.0"`, `pyproject.toml` (setuptools,
  `py-modules` `ai_contexts` and `ai_contexts_test`, commands
  `ai_contexts` and `aic`, dynamic version), `LICENSE` (MIT-0, copied
  from `ezpkg`; the user has not approved it yet), build output in
  `.gitignore`/`.hgignore`, and `_permissions_ignored()` in the tests
  (no `os.geteuid` on Windows).
* `release_check.py source|testpypi VERSION|pypi VERSION`: new venv, new
  HOME, installs the wheel, runs the installed `ai_contexts --test` and
  an `aic` session.  Passes locally on 3.11-3.15 (uv Pythons).
* `.github/workflows/check.yml` (lint for `source`; stranger matrix of
  4 OS x 5 Pythons) and `release.yml` (build with `dev` version for
  testpypi, `GITHUB_REF` tag check for pypi; publish; listed; check).
  `actionlint` clean; build steps rehearsed locally.
* GitHub settings by `gh api`, read back: environments `testpypi`
  (branch `main`) and `pypi` (tag `v*`), reviewer waynegramlich;
  ruleset 25837137 "release tags".
* Still needed: the user's commit and OK to push; then `check.yml`
  `source` run (Windows will likely fail on read-only rule copies);
  PyPI pending publishers (web); the user's go for each upload.

## First `check.yml` run (2026-10-25)

* check.yml 40234244435 (`source`, dd80f49): lint passed; 13/20
  stranger jobs.  Failed: macOS 3.11 (both; `Path.glob()` at `/` hit
  `/.resolve`, `EINVAL`), Windows (all 5; read-only `Details.md` can not
  be deleted; paths printed with `\`).
* Fixed: `collections_in()` (an `iterdir()` loop that skips entries it
  can not check) for `find_collections()`; `write_file()` writes `\n`;
  `make_writable()`, `remove_file()`, `remove_tree()` for read-only rule
  copies (refresh, `source`, `upgrade_rule()`, `delete`); `as_posix()`
  for the paths `update_references()` prints; tests use `remove_file()`
  and have `_test_portability()` (570 checks).  Needs the user's
  commit and push for the next run.
* `ezpkg`: rule 5 now `R.gwr` from `../aicontexts/rule_sources/
  GitHub_Workflow_Rules.md`; `solidcraft`: `ai_contexts` link fixed.
  Both moved to the new rules layout (not committed there).
* Example rule directory in `README.md`, `REFERENCE.md` and `RULES_TEXT` is now `../shared_rules/` (was `../claude_code_rules/`, which the user will delete); closed items left as history.  `solidcraft` rules now come from `../aicontexts/rule_sources/`.
* check.yml 40239306320 (ebf09b2): 16/21 (lint, Linux, macOS all
  pass).  Windows: 530 checks, 2 failures: doubtful sources printed
  with `\` (`screen_sources()`), and reference files sorted
  case-insensitively by `WindowsPath`.  Fixed with `as_posix()` and
  `key=Path.as_posix` (also in `tag_references()` and
  `collections_in()`).

## `aic r copy` (2026-10-25, the user's design)

* `README.md`'s rules example no longer worked for another project's
  rules (every copy is `Details.md`, a reserved name).  Added `copy
  DIRECTORY [CHOICES...]`: lists a rules collection's rules (by number;
  read, never loaded) or a directory's `.md` files, titled by the first
  `# ` line (else `.item.json`, else the name), marks `(have it)` (same
  source or same text), takes comma or space separated numbers and
  `FROM-TO` ranges (asked if not given), screens them like `create`,
  and creates them after the last rule, InActive.  `is_rule_copy()`
  lets such a `Details.md` be a source.  State commands now take a
  range of siblings (for the `activate` hint).  `_test_rule_copy()`;
  597 checks, full coverage.  Docs: `-h`, `RULES_TEXT`, `README.md`,
  `REFERENCE.md`.
* The user's `aic r copy` in `../solidcraftcnc` failed: its `RULES/` had
  no type, so `copy` was "Unknown".  Now `NAME create` makes a `RULES`
  collection (any case) a rules collection, and a command of the other
  type says so and how to change the type (`other_type_error()`).
  `README.md` and `REFERENCE.md` drop the `r type rules` step.  601
  checks.  Rehearsed the README steps in a scratch `solidcraftcnc`.
* check.yml 40244792000 (9f69293): 16/21; Windows 561 checks, 2 failures: `copy` printed `..\none`.  Typed paths in `copy`, `expand_files()`, `source_name_error()` and `set_source()` now use `as_posix()`.
* check.yml 40248621774 (8fb08f1): 21/21 (lint; Linux, Windows, macOS
  Apple Silicon and Intel; Python 3.11-3.15).  The portability traps
  went into `R.gwr` ("What the Other Systems Find").
* Next: PyPI pending publishers (the user, on the web), then the
  user's go for a testpypi `release.yml` run, then for pypi.

## Paused (2026-10-25, end of session)

* The user committed the `R.gwr` "What the Other Systems Find" notes as
  `638a43e` (its push is the user's, before `/clear`).
* Nothing has been uploaded anywhere.  To resume, in order:
  1. The user adds the two PyPI pending publishers (project
     `aicontexts`, owner `waynegramlich`, repository `aicontexts`,
     workflow `release.yml`, environment `testpypi` on test.pypi.org
     and `pypi` on pypi.org), only once `aicontexts`/`solidcraft` have
     settled (the user's #4).
  2. On the user's explicit go: `gh workflow run release.yml -f
     target=testpypi`, approve it (`R.gwr` "Approving a Deployment"),
     watch it and its `check` job; record the run id here.
  3. On a separate go: tag `v0.1.0` (the user), `gh workflow run
     release.yml --ref v0.1.0 -f target=pypi`, then `./release_check.py
     pypi 0.1.0` locally.
* The user was still trying the README steps in `../solidcraftcnc`.

## Ready to rehearse (2026-10-26)

* The user approved `LICENSE` (MIT-0) and pushed `e5e2541`; git clean,
  `git ls-remote github main` matches.  Code unchanged since the green
  check.yml 40248621774 (8fb08f1; only `rule_sources/` differ).  All
  four checkers clean, 601 checks.  Next: pending publishers (the
  user), then the testpypi go.
* release.yml 40391568647 (`testpypi`, e5e2541): build, publish,
  listed, check 20/20 (lint skipped for a version) all passed;
  test.pypi.org has `0.1.0.dev202610261959`.  `./release_check.py
  testpypi 0.1.0.dev202610261959` passed locally.  Next: pypi.org
  pending publisher (the user), tag `v0.1.0`, the user's go for pypi.
* The user: Claude may run every `git` command except `git commit`
  (`R.vcr` source updated).  pypi.org pending publisher added (the
  user).  Claude tagged `v0.1.0` (annotated, 7433c92) on e5e2541 and
  pushed it; `git ls-remote` confirms.  Next: the user's go for pypi.

## Released (2026-10-26)

* release.yml 40399623382 (`pypi`, v0.1.0 = e5e2541): build, publish,
  listed, check 20/20 passed.  pypi.org has `aicontexts` 0.1.0 (wheel
  and sdist).  `./release_check.py pypi 0.1.0` passed locally.
