# Claude Code Session Rules

The Claude Code Session rules are:
* Coding sessions are broken into planned steps labeled `#Sn`, where `n` is a
  positive integer starting from 1.  Coding plans are not rigid; they can be
  changed and rearranged as needed.  In general, at the end of a Step, the
  AI context is saved into a file and a `git commit` and `git push` is
  performed.  It may be followed by a `/clear`.
* In order to conserve tokens, a coding Step is broken into smaller chunks
  of effort.  These effort chunks are typically limited to a modest number of
  minutes (e.g. 3 minutes).  After each chunk, report the tokens
  remaining, as a percentage of those available when the session started.
* Any issues that come up are given a sticky unique number, counting up
  from #1.  Each new issue gets a new number and resolved issue numbers
  do not get reused.  When asked for a prioritized issue list, just list the
  issues from most important to least important without prefixing by priority
  number.  A common request is to ask for the top N issues (e.g. 5).
* Save a session transcript in `~/.claude_transcriptions/` using the start
  time and the project's name, as `YYYY-MM-DD_HH:MM_PROJECT.md`.  After
  each git commit, update the current transcript content.
