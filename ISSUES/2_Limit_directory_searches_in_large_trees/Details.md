# 2 Limit directory searches in large trees

Some development trees are huge, and `ai_contexts` can not search all of
them, so its searches need limits.  There are two searches:

* Up: `find_collections()` lists every sub-directory of the current
  directory and then of each parent, up to `/`, until one holds a
  collection.  Outside a project, it reads every directory above it, and
  it can find an unrelated collection in an ancestor directory.
* Down: `tag_references()` (used when a rename or transfer changes a
  tag) walks the whole tree below the directory that holds the
  collections, skipping only hidden directories and symbolic links, and
  reads every writable `.md` file.  In a big tree (e.g. with
  `node_modules/` or a build directory) that can take a long time.

Possible limits: stop the upward search at a version control root
(`.git`, `.hg`) or the home directory; skip known-large directories or
honor `.gitignore`; cap the depth or the number of files and say so;
or let `.ai_contexts.json` list the directories to search.
