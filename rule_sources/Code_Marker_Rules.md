# Code Marker Rules

<!-- --------------------------- 79 characters ---------------------------- -->

Put a marker comment directly before every Python function, class, and
method (above any decorators, same indentation, preceded by the blank
lines PEP 8 requires: two at the top level, one inside a class):

* Function: ``# Function `function_name()`:``
* Class: ``# Class `ClassName`:``
* Method: ``# Method `ClassName.method_name()`:``

Parentheses are always empty.  Use the defining class's name for
overridden methods.  Keep markers in sync when renaming.  Nested
functions and classes (and their methods) get no marker.  A marker may
exceed 72 characters if the name requires it.

Test suite files are exempt from these rules.  These rules require
`Python_Coding_Rules.md`, which defines test suite files.
