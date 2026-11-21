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
* Every session has a transcript in `~/.claude_transcripts/`, named
  by the session's start time and the project's name, as
  `YYYY-MM-DD_HH:MM_PROJECT.md`.  Claude writes it (and rewrites it,
  to the same name) by running, from the project:
  `python3 ~/public_html/projects/aicontexts/transcripts/session_transcript.py`,
  which prints its path.  The scripts are kept in `aicontexts`'s
  `transcripts/`; only the transcripts go in `~/.claude_transcripts/`.
* Claude's first tool call of every session, before anything else
  and whatever the user's first message asks, is that command; the
  first reply gives the transcript's path.
* Claude runs it again whenever the user's message contains `git
  commit`, after each commit, and before each `/clear`, and gives the
  path each time.
