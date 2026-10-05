# Tracker: General Purpose Tool for Tracking Items

The `tracker` program manages a directory of Item's.  It can be used to manage
Issue's (i.e. bugs), Task's (i.e. a chunk of work), etc.

Each Item is stored in a dedicated sub-directory following information:
* Title:
  A short one line description of the item (e.g. `Initialization Fails`.)
* Number:
  A unique hierarchical number (e.g. `1.2.3`) used for sorting.
* State:
  The state of the (e.g. Pending, Open, Suspended, Closed.)
* `Details.md`:
  A file edited by a human that textually describes the item.
* `Context.md`:
  A file managed by an AI LLM that has additional AI context information.
The tracker also creates and updates a file called `STARTUP.md` that contains
context saved by a previous AI session.
