# LLM Agent Context Log

Design (2026-10-09, agreed with the user after rejecting budgets,
breadth-first walks, `git ls-files` and skip lists as too complex):
* Up: `find_collections()` uses `directory.glob("*/.ai_contexts.json")`
  in each directory going up, and stops after the first directory that
  has `.git` or `.hg` (still checking that directory itself); with
  neither it goes to `/`.  Other version control systems are not
  assumed.
* Down: `tag_references()` searches only each collection (recursively,
  `rglob("*.md")`) and the `.md` files directly in the project
  directory (`glob("*.md")`); `update_references()` prints a `grep`
  hint for everything else.
* Always sort glob results (deterministic: no clock, same answer until
  the file system changes).  Always check for symbolic links, in every
  path component, since they can warp the search anywhere;
  `glob.glob(recursive=True)` follows linked directories, and
  `pathlib.rglob()` does not in 3.12 but has changed across versions.
