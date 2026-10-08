# Python Markdown Comments

The Markdown specification basically evolved from the informal plain-text
E-mail and Usenet postings.  It is a fairly simple format that is easily read
by both people and computers, particularly large language models.
In Python, it is really easy to write both documentation strings (`"""..."""`)
and inline comments (`# ...`) in Markdown format.

## Google Python Style Guide Tweaks for Markdown.

Google has produced a
[Python Style Guide](https://google.github.io/styleguide/pyguide.html).
Section 3.8 (Comments and Docstrings) in the style guide discusses a reasonable
format for documenting a Python module (i.e. a `.py` file) and its associated
functions classes, and methods.

In summary:
* Section 3.7 - Shebang Line:
  For a Python module (i.e. a Python files with a suffix of `.py`) that is
  meant to be directly executable, the first line can start with `
  #!/usr/bin/env python3`.  See [Pep-394](https://peps.python.org/pep-0394/).
  This line is skipped if the Python module is not meant to be directly
  executable.  On Linux and MacOS, this file should probably have the execute
  bit turned on as well.
* Section 3.8.1 - Documentation Strings:
  Documentation strings (i.e. "docstring's") are supposed to written using
  triple double quotes (i.e. `""" ... """`).  The first `"""` is immediately
  followed without any intervening spaces by a one line summary of the Python
  module (i.e. file), function, class or method.  This is followed by followed
  by a blank line and further module description.

  For example:
  ```python
  """#!/usr/bin/env python3
  A one-line summary of the module or program, terminated by a period.

  Leave one blank line following the summary.  The rest of the docstring
  should contain one or more Markdown paragraphs (separated by a blank line)
  that provides an overall description of the module or program.

  The closing quotes `"""` should be on its own line, followed by a blank line.
  """
  ```
* Section 3.8.2 - Modules:
  This style guide section discusses the first documentation string at the very
  front of a Python file.  The first line is the module summary line,
  optionally followed by a blank line and one or more paragraphs of discussion
  about the entire module.  All of the is easily written in Markdown.
* Section 3.8.3 (Functions, Classes and Methods):
  The style guide specifies the structure on the documentation at the front
  of each Python function, class and method:
  * One line summary:
    The one line summary summarizes what the function/method does in the first
    line.  It is followed by a blank line.
  * `Args`:  While the style guide suggests using `Args:` as the first
    line in arguments section, `Arguments:` works just as well.  While the
    style  guide only lists the argument name followed by some descriptive
    text, it somewhat more informative to follow the name with Python type in
    parentheses and colon (`:`).  Further lines of argument description can
    follow.
  * `Returns or Yields`: The return value(s) for functions and yield values for
    iterators.  Again it does not hurt to add the type in parentheses.
  * `Raises`: Each possible exception is listed.
  That is pretty much it.

  A simple (but contrived) example is shown immediately below:
    ```python
    # Example function:
    def divide(dividend: int, divisor: int) -> int:
        """Divide two integers.

        Arguments:
        * `dividend` (`int`):
          The number to divide
        * `divisor` (`int`):
          The number to divide by.

        Returns:
        * (`int`): The quotient of the division
        """

        Raises:
	* `ZeroDivisionError`
        """	
        if divisor == 0:
	    raise ZeroDivisionError
        return a + b
    ```
* Section 3.8.2 - Classes
  This section of the document does not say much.  It basically says the class
  attributes should be documented under an `Attributes:` section.  Thus, for
  markdown , it looks basically as follows:
     ```python
     class SampleClass:
         """ One-line Summary goes here.

         More multi line documentation goes here.

         Attributes:
	 * `likes_spam` (`bool`): True if we like SPAM.
	 * `eggs` (`int`): The number eggs laid.

         Constructor:
	 * `SampleClass(likes_spam, eggs)`
     ```
  The `Constructor:` section is added because it can be difficult to can be
  difficult to figure out what the actual initialization arguments are when
  the class is preceded by the "@dataclass" decorator.  Speaking the
  `@dataclass" decorator, consider using `@dataclass(slots=True)` to reduce
  memory usage slightly speeding up attribute access..  Also, if the class
  no natural order for the attributes, consider just alphabetizing them
  consider replacing with `Attributes:` with `Attributes (alphabetized):`
  instead.

## Some Additional Non-Markdown Centric Coding Suggestions.

Here are some additional suggestions:
1. This seems obvious, but it is worth mentioning.  In general, Python comments
   should be written in English sentences with the first word capitalized, and
   ending with a period (or question mark.)  Since, all modern editors have a
   mode that enables spell checking, there is really is no reason for
   misspelled words in Python documentation strings or comments.
2. All lines 79 must be characters or less as specified by PEP 8.  Sometimes,
   Markdown has no way to avoid violating this rule (e.g. long hypertext links,
   code blocks enclosed in Markdown triple back quotes, etc.)
3. When referencing the variable, function, class and method names inside of
   comments, enclose them in back quotes.  For example, `my_func`, `my_class`,
   `my_variable`, etc.)
5. Use Python type hints and run the `mypy` (Python lint program.)  It catches
   lots of issues.  In general, **ALL** python variables should have valid
   type hint.  `Any` should only be used as a last resort.  Note that type
   hints can be enclosed in quotes.  One way to determine the type is to
   use the `type()` function and use a quotes string.  Alternatively, define
   the type `NewType`="result of type() function."
6. Use the `ruff check` program.  It seems pretty safe to run either
   `ruff check` or `ruff check --fix` to automatically fix simple errors.
7. A common coding style is to have blocks of code separated by blank line.
   It is really useful to put 1 or 2 line hash (i.e. `#`) comments at the
   front of each code block.
