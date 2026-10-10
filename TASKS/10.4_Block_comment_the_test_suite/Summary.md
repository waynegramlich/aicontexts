# Summary of `T.bcts` Block comment the test suite

`R.pcr` now puts its block-comment rule ahead of the test suite
exemption, so the rule applies to test suites.  Added 201 block
comments to `ai_contexts_test.py` (none on nested functions, matching
`ai_contexts.py`), plus blank lines before 5 existing comments that
start a block.  The `T.fpcr` summary now says the exemption was
dropped.  The test suite exemption itself (from the `Python` section
on) was reworded in `../claude_code_rules/Python_Coding_Rules.md`.
