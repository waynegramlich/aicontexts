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
* Then `R.gar`: `check.yml`, `release.yml`, PyPI.

## Upstream (2026-10-25)

* The user pushes with a plain `git push`: `branch.main.remote github`
  and `branch.main.merge refs/heads/main` set by `git config`
  (`--set-upstream-to` needs `github/main` to exist); `git push
  --dry-run` showed `* [new branch] main -> main`.  Added to `R.gsr`
  step 5.
