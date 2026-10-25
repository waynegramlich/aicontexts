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
