import os
import sys
import re
import doctest
import tempfile
import unicodedata
from doctest import (
    _load_testfile,
    _SpoofOut,
    _indent,
    _exception_traceback,
    register_optionflag,
    _extract_future_flags,
    _OutputRedirectingPdb,
    Example,
    linecache,
    SKIP,
    TestResults,
    REPORT_ONLY_FIRST_FAILURE,
    master,
)

try:
    from doctest import FAIL_FAST
except ImportError:
    FAIL_FAST = register_optionflag("FAIL_FAST")

try:
    from shlex import quote as sh_quote, split as sh_split
except ImportError:

    def sh_quote(string):
        return string

    def sh_split(string):
        return string.split()


import pdb
import scripttest

CREATE_FILE_BEFORE_TEST = register_optionflag("CREATE_FILE_BEFORE_TEST")
CHANGE_DIRECTORY = register_optionflag("CHANGE_DIRECTORY")


######################################################################
# 3. ScriptDocTest Parser
######################################################################


class ScriptDocTestParser(doctest.DocTestParser):
    """
    A class used to parse strings containing scriptdoctest examples.
    """

    # This regular expression is used to find doctest examples in a
    # string.  It defines three groups: `source` is the source code
    # (including leading indentation and prompts); `indent` is the
    # indentation of the first (PS1) line of the source code; and
    # `want` is the expected output (including leading indentation).
    _EXAMPLE_RE = re.compile(
        r"""(
        # Source consists of ::, an empty line, and then a PS1 line
        # followed by indented or blank lines. Splitting out
        # separate commands and their sources and wants is an issue
        # for the single-example parser.
        ::[ \n]*
        (?P<example>
            (?:^(?P<indent> [ ]*) \$[ ] .*\n)  # PS1 line
            (?:((?P=indent)       .*      \n)|
               ([ ]*                      \n))*)
        \n?
        )|(
        # Alternatively, we also need to consider file content examples.
        ^(?P<preindent> [ ]*) ::\n
        (?P<options>(
            ([ ]*\n)|
            (?P=preindent)[#] .*\n)*)
        (?P<content>
            ((?P<fullindent> (?P=preindent)[ ]+).*\n)*)
        \n?
        (?P=preindent) ---? [ ]* (?P<filename> .*)$
        )""",
        re.MULTILINE | re.VERBOSE,
    )

    # A regular expression for handling `want` strings that contain
    # expected exceptions.  It divides `want` into three pieces:
    #    - the traceback header line (`hdr`)
    #    - the traceback stack (`stack`)
    #    - the exception message (`msg`), as generated by
    #      traceback.format_exception_only()
    # `msg` may have multiple lines.  We assume/require that the
    # exception message is the first non-indented line starting with a word
    # character following the traceback header line.
    _EXCEPTION_RE = re.compile(
        r"""
        # Grab the traceback header.  Different versions of Python have
        # said different things on the first traceback line.
        ^(?P<hdr> Traceback\ \(
            (?: most\ recent\ call\ last
            |   innermost\ last
            ) \) :
        )
        \s* $                # toss trailing whitespace on the header.
        (?P<stack> .*?)      # don't blink: absorb stuff until...
        ^ (?P<msg> \w+ .*)   #     a line *starts* with alphanum.
        """,
        re.VERBOSE | re.MULTILINE | re.DOTALL,
    )

    def get_doctest(self, string, globs, name, filename, lineno):
        """
        Extract all doctest examples from the given string, and
        collect them into a `DocTest` object.

        `globs`, `name`, `filename`, and `lineno` are attributes for
        the new `DocTest` object.  See the documentation for `DocTest`
        for more information.
        """
        return doctest.DocTest(
            self.get_examples(string, name), globs, name, filename, lineno, string
        )

    def _parse_example(self, m, name, lineno):
        """
        Given a regular expression match from `_EXAMPLE_RE` (`m`),
        return a pair `(source, want)`, where `source` is the matched
        example's source code (with prompts and indentation stripped);
        and `want` is the example's expected output (with indentation
        stripped).

        `name` is the string's name, and `lineno` is the line number
        where the example starts; both are used for error messages.
        """

        # The regex matches both code examples and file
        # constructions. Code examples are indented by `indent`.
        if m.group("indent"):
            # Get the example's indentation level.
            indent = len(m.group("indent"))

            # Divide source into lines; check that they're properly
            # indented; and then strip their indentation & prompts.
            lines = m.group("example").split("\n")[:-1]

            source = ""
            want = []
            example_lineno = 0
            # Parse line by line into separate examples
            for l, line in enumerate(lines):
                if not line.strip():
                    line = ""
                else:
                    line = line[4:]
                if line.startswith("$ "):
                    if self._IS_BLANK_OR_COMMENT(source):
                        pass
                    else:
                        # Extract options from the source.
                        options = self._find_options(source, name, lineno)
                        yield Example(
                            source,
                            "\n".join(want),
                            "",
                            lineno=lineno + example_lineno,
                            indent=indent,
                            options=options,
                        )
                    source = line[2:]
                    want = []
                    example_lineno = l
                elif line.startswith("> "):
                    if want:
                        want.append(line)
                    else:
                        source = "{:}\n{:}".format(source, line[2:])
                else:
                    want.append(line)

            # Construct the last example.
            # Extract options from the source.
            options = self._find_options(source, name, lineno)
            yield Example(
                source,
                "\n".join(want),
                "",
                lineno=lineno + example_lineno,
                indent=indent,
                options=options,
            )
        # File constructions, on the other hand, don't match that
        # branch of the regular expression. Instead, they are have two
        # other indentation levels, but `preindent` is only used to
        # find the corresponding file name after it.
        elif m.group("preindent"):
            indent = len(m.group("fullindent"))

            # Divide file into lines; check that they're properly
            # indented; and then strip their indentation.
            file_lines = m.group("content").split("\n")
            self._check_prefix(file_lines, " " * indent, name, lineno)
            file_content = "\n".join([fl[indent:] for fl in file_lines])

            # The file name is just that, stripped.
            filename = m.group("filename")

            options = self._find_options(m.group("options"), name, lineno)
            options[CREATE_FILE_BEFORE_TEST] = True

            yield Example(
                "cat {:s}".format(sh_quote(filename)),
                file_content,
                None,
                lineno=lineno,
                indent=indent,
                options=options,
            )

    def parse(self, string, name="<string>"):
        """
        Divide the given string into examples and intervening text,
        and return them as a list of alternating Examples and strings.
        Line numbers for the Examples are 0-based.  The optional
        argument `name` is a name identifying this string, and is only
        used for error messages.
        """
        string = string.expandtabs()
        # If all lines begin with the same indentation, then strip it.
        min_indent = self._min_indent(string)
        if min_indent > 0:
            string = "\n".join([l[min_indent:] for l in string.split("\n")])

        output = []
        charno, lineno = 0, 0
        # Find all doctest examples in the string:
        for m in self._EXAMPLE_RE.finditer(string):
            # Add the pre-example text to `output`.
            output.append(string[charno : m.start()])
            # Update lineno (lines before this example)
            lineno += string.count("\n", charno, m.start())
            # Extract info from the regexp match and create an Example
            for example in self._parse_example(m, name, lineno):
                output.append(example)
            # Update lineno (lines inside this example)
            lineno += string.count("\n", m.start(), m.end())
            print(lineno)
            # Update charno.
            charno = m.end()
        # Add any remaining post-example text to `output`.
        output.append(string[charno:])
        return output

    def _check_prompt_blank(self, lines, indent, name, lineno):
        """Do nothing.

        In ScriptDocTest, we ensure that every prompt is followed by a
        space character in the regular expression looking for prompts,
        because otherwise we might get too many false positives. So we
        don't need to check that again.

        """
        pass


######################################################################
# 4. EllipsisOutputChecker
######################################################################

ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class EllipsisOutputChecker(doctest.OutputChecker):
    """A class for comparing real and expected output.

    `EllipsisOutputChecker` checks whether the actual output from a
    doctest example matches (including ellipsis consideration) the
    expected output. It defines two methods: `check_output`, which
    compares a given pair of outputs, and returns true if they match;
    and `output_difference`, which returns a string describing the
    differences between two outputs.

    """

    @staticmethod
    def ellipsis_match(want, got):
        """Check for a match up to ellipsis

        Return True iff the actual output from an example (`got`)
        matches the expected output (`want`). These strings are always
        considered to match if they are identical; The regex
        "\[\.\.\.[^]]*\]\n?", that is "[...]" or something like "[... more
        lines]" in `want` may match any substring in `got`. If such an
        ellipsis expression is on a separate line, it can match any
        number (including 0) of lines.

        A subtle case:

            >>> EllipsisOutputChecker.ellipsis_match("aa[...]aa", "aaa")
            False

            >>> EllipsisOutputChecker.ellipsis_match(
            ... '''Text A
            ... [...]
            ... Text B''',
            ... '''Text A
            ... Text B''')
            True

            >>> EllipsisOutputChecker.ellipsis_match(
            ... '''Text A
            ... [...]
            ... Text B''',
            ... '''Text A Text B''')
            False

            >>> EllipsisOutputChecker.ellipsis_match(
            ... '''[...]
            ... Test
            ... [...]''',
            ... '''Test''')
            True

            >>> EllipsisOutputChecker.ellipsis_match(
            ... '''[...]''',
            ... '''This
            ... text''')
            True

            >>> EllipsisOutputChecker.ellipsis_match(
            ... '''[... Some lines of code]
            ... tests
            ... [...]''',
            ... '''Here we have
            ... text and some
            ... tests
            ... ''')
            True

        """
        if "[..." not in want:
            return want == got

        want = want + "\n"
        got = got + "\n"

        # Find "the real" strings.
        raw_ws = want.split("[...")
        assert len(raw_ws) >= 2

        # Find the closing brackets
        ws = [raw_ws[0]]
        for w in raw_ws[1:]:
            i = w.index("]")
            if len(w) > i + 1 and w[i + 1] == "\n":
                ws.append(w[i + 2 :])
            else:
                ws.append(w[i + 1 :])

        # Deal with exact matches possibly needed at one or both ends.
        startpos, endpos = 0, len(got)
        w = ws[0]
        if w:  # starts with exact match
            if got.startswith(w):
                startpos = len(w)
                del ws[0]
            else:
                return False
        w = ws[-1]
        if w:  # ends with exact match
            if got.endswith(w):
                endpos -= len(w)
                del ws[-1]
            else:
                return False

        if startpos > endpos:
            # Exact end matches required more characters than we have, as in
            # _ellipsis_match('aa...aa', 'aaa')
            return False

        # For the rest, we only need to find the leftmost non-overlapping
        # match for each piece.  If there's no overall match that way alone,
        # there's no overall match period.
        for w in ws:
            # w may be '' at times, if there are consecutive ellipses, or
            # due to an ellipsis at the start or end of `want`.  That's OK.
            # Search for an empty string succeeds, and doesn't change startpos.
            startpos = got.find(w, startpos, endpos)
            if startpos < 0:
                return False
            startpos += len(w)

        return True

    def check_output(self, want, got, optionflags):
        """
        Return True iff the actual output from an example (`got`)
        matches the expected output (`want`).  These strings are
        always considered to match if they are identical; but
        depending on what option flags the test runner is using,
        several non-exact match types are also possible.  See the
        documentation for `TestRunner` for more information about
        option flags.
        """

        print(optionflags)

        # If `want` contains no ANSI C1 escape sequences, but `got` is
        # generated with them eg. from a program that uses color output, they
        # will not match but should. To normalize, strip the escape sequences
        # from both.

        # In addition, we normalize the unicode form, and if there are carriage
        # returns on a line, we assume they indeed reset the line.
        got = ansi_escape.sub('', got)
        got = unicodedata.normalize("NFC", got)
        got = got.replace("\t", "    ")
        got = '\n'.join(
            line.rsplit("\r", 1)[-1]
            for line in got.split("\n")
            )

        want = ansi_escape.sub('', want)
        want = unicodedata.normalize("NFC", want)
        want = want.replace("\t", "    ")

        # Handle the common case first, for efficiency:
        # if they're string-identical, always return true.
        if got == want:
            return True

        # This flag causes doctest to ignore any differences in the
        # contents of whitespace strings.  Note that this can be used
        # in conjunction with the ELLIPSIS flag.
        if optionflags & doctest.NORMALIZE_WHITESPACE:
            got = " ".join(got.split())
            want = " ".join(want.split())
            if got == want:
                return True

        # The ELLIPSIS flag says to let the regex "\[\.\.\.[^]]*\]",
        # that is [...] or something like [... more lines] in `want`
        # match any substring in `got`. If such an ellipsis expression
        # is on a separate line, it can match any number (including 0)
        # of lines.
        if optionflags & doctest.ELLIPSIS:
            if self.ellipsis_match(want, got):
                return True

        return False


######################################################################
# 5. ScriptDocTest Runner
######################################################################


class ScriptDocTestRunner(doctest.DocTestRunner):
    """A class used to run DocTest test cases for scripts, and accumulate
    statistics.  The `run` method is used to process a single DocTest
    case.  It returns a tuple `(f, t)`, where `t` is the number of
    test cases tried, and `f` is the number of test cases that failed.

        >>> tests = doctest.DocTestFinder().find(_TestClass)
        >>> runner = doctest.DocTestRunner(verbose=False)
        >>> tests.sort(key = lambda test: test.name)
        >>> for test in tests:
        ...     print(test.name, '->', runner.run(test))
        _TestClass -> TestResults(failed=0, attempted=2)
        _TestClass.__init__ -> TestResults(failed=0, attempted=2)
        _TestClass.get -> TestResults(failed=0, attempted=2)
        _TestClass.square -> TestResults(failed=0, attempted=1)

    The `summarize` method prints a summary of all the test cases that
    have been run by the runner, and returns an aggregated `(f, t)`
    tuple:

        >>> runner.summarize(verbose=1)
        4 items passed all tests:
           2 tests in _TestClass
           2 tests in _TestClass.__init__
           2 tests in _TestClass.get
           1 tests in _TestClass.square
        7 tests in 4 items.
        7 passed and 0 failed.
        Test passed.
        TestResults(failed=0, attempted=7)

    The aggregated number of tried examples and failed examples is
    also available via the `tries` and `failures` attributes:

        >>> runner.tries
        7
        >>> runner.failures
        0

    The comparison between expected outputs and actual outputs is done
    by an `OutputChecker`.  This comparison may be customized with a
    number of option flags; see the documentation for `testmod` for
    more information.  If the option flags are insufficient, then the
    comparison may also be customized by passing a subclass of
    `OutputChecker` to the constructor.

    The test runner's display output can be controlled in two ways.
    First, an output function (`out) can be passed to
    `TestRunner.run`; this function will be called with strings that
    should be displayed.  It defaults to `sys.stdout.write`.  If
    capturing the output is not sufficient, then the display output
    can be also customized by subclassing DocTestRunner, and
    overriding the methods `report_start`, `report_success`,
    `report_unexpected_exception`, and `report_failure`.

    """

    # This divider string is used to separate failure messages, and to
    # separate sections of the summary.
    DIVIDER = "*" * 70

    def __init__(self, checker=None, verbose=None, optionflags=0, base_path=None):
        """
        Create a new test runner.

        Optional keyword arg `checker` is the `OutputChecker` that
        should be used to compare the expected outputs and actual
        outputs of doctest examples.

        Optional keyword arg 'verbose' prints lots of stuff if true,
        only failures if false; by default, it's true iff '-v' is in
        sys.argv.

        Optional argument `optionflags` can be used to control how the
        test runner compares expected output to actual output, and how
        it displays failures.  See the documentation for `testmod` for
        more information.
        """
        self._checker = checker or EllipsisOutputChecker()
        if verbose is None:
            verbose = "-v" in sys.argv
        self._verbose = verbose
        self.optionflags = optionflags
        self.original_optionflags = optionflags

        # Keep track of the examples we've run.
        self.tries = 0
        self.failures = 0
        self._name2ft = {}

        # Create a fake output target for capturing doctest output.
        self._fakeout = _SpoofOut()

        if base_path:
            self.directory = base_path
        else:
            self.directory = None

    # Reporting methods

    def report_unexpected_exception(self, out, test, example, exc_info):
        """
        Report that the given example raised an unexpected exception.
        """
        out(
            self._failure_header(test, example)
            + "Exception raised:\n"
            + _indent(_exception_traceback(exc_info))
        )

    def _failure_header(self, test, example):
        out = [self.DIVIDER]
        if test.filename:
            if test.lineno is not None and example.lineno is not None:
                lineno = test.lineno + example.lineno + 1
            else:
                lineno = "?"
            out.append('File "%s", line %s, in %s' % (test.filename, lineno, test.name))
        else:
            out.append("Line %s, in %s" % (example.lineno + 1, test.name))
        out.append("Failed example:")
        source = example.source
        out.append(_indent(source))
        return "\n".join(out)

    # util
    def __patched_linecache_getlines(self, filename, module_globals=None):
        m = self.__LINECACHE_FILENAME_RE.match(filename)
        if m and m.group("name") == self.test.name:
            example = self.test.examples[int(m.group("examplenum"))]
            return example.source.splitlines(keepends=True)
        else:
            return self.save_linecache_getlines(filename, module_globals)

    # DocTest Running

    def __run(self, test, compileflags, out):
        """
        Run the examples in `test`.  Write the outcome of each example
        with one of the `DocTestRunner.report_*` methods, using the
        writer function `out`.  `compileflags` is the set of compiler
        flags that should be used to execute examples.  Return a tuple
        `(f, t)`, where `t` is the number of examples tried, and `f`
        is the number of examples that failed.  The examples are run
        in the namespace `test.globs`.
        """
        # Keep track of the number of failures and tries.
        failures = tries = 0

        # Save the option flags (since option directives can be used
        # to modify them).
        original_optionflags = self.optionflags

        SUCCESS, FAILURE, BOOM = range(3)  # `outcome` state

        check = self._checker.check_output

        testenvironment = scripttest.TestFileEnvironment(base_path = self.directory)

        # Process each example.
        for examplenum, example in enumerate(test.examples):

            # If REPORT_ONLY_FIRST_FAILURE is set, then suppress
            # reporting after the first failure.
            quiet = self.optionflags & REPORT_ONLY_FIRST_FAILURE and failures > 0

            # Merge in the example's options.
            self.optionflags = original_optionflags
            if example.options:
                for (optionflag, val) in example.options.items():
                    if val:
                        self.optionflags |= optionflag
                    else:
                        self.optionflags &= ~optionflag

            # If 'SKIP' is set, then skip this example.
            if self.optionflags & SKIP:
                continue

            # Record that we started this example.
            tries += 1
            if not quiet:
                self.report_start(out, test, example)

            # Run the example in the given context (globs), and record
            # any exception that gets raised.  (But don't intercept
            # keyboard interrupts.)

            if self.optionflags & CREATE_FILE_BEFORE_TEST:
                split = sh_split(example.source)
                if split[0] == "cat" and (
                    len(split) == 2 or len(split) >= 3 and split[2].startswith("#")
                ):
                    filename = split[1]
                    with open(
                        os.path.join(testenvironment.cwd, filename), "w"
                    ) as file_to_write:
                        file_to_write.write(example.want)
                else:
                    raise ValueError(
                        "Example requested file creation, "
                        "which works only if the command is of the form "
                        "`$ cat 'literal_filename'`",
                        example.source,
                    )

            by_python_pseudoshell = False
            if self.optionflags & CHANGE_DIRECTORY:
                split = sh_split(example.source)
                if split[0] == "cd" and (
                    len(split) == 2 or len(split) > 2 and split[2].startswith("#")
                ):
                    dirname = os.path.join(testenvironment.cwd, split[1])
                    if os.path.exists(dirname) and os.path.isdir(dirname):
                        testenvironment.cwd = dirname
                        got = ""
                        by_python_pseudoshell = True
                        exception = 0
                elif split[0] == "export" and (
                    len(split) == 2 or len(split) > 2 and split[2].startswith("#")
                ):
                    variable, value = split[1].split("=")
                    testenvironment.environ[variable] = value
                    by_python_pseudoshell = True
                    got = ""
                    exception = 0

            if example.source.startswith("python -m"):
                data_file = os.path.abspath("./.coverage")
                coverage_file = os.path.abspath("./.coveragerc")
                with open(coverage_file, "w") as coveragerc:
                    coveragerc.write(f"""[run]
branch=True
data_file={data_file:}""")
                example.source = example.source.replace("python -m", f"coverage run -a --source lexedata --rcfile={coverage_file} -m")

            if not by_python_pseudoshell:
                # Don't blink!  This is where the user's code gets run.
                try:
                    # testenvironment does not run in shell mode. It's
                    # better explicit than implicit anyway.
                    output = testenvironment.run(
                        "/bin/sh",
                        "-c",
                        example.source,
                        expect_error=True,
                        err_to_out=True,
                    )

                    self.debugger.set_continue()
                    # ==== Example Finished ====
                    exception = output.returncode
                except KeyboardInterrupt:
                    raise

                got = output.stdout  # the actual output
                self._fakeout.truncate(0)

            outcome = FAILURE  # guilty until proven innocent or insane

            # If the example executed without raising any exceptions,
            # verify its output.
            if exception == 0:
                if check(example.want, got, self.optionflags):
                    outcome = SUCCESS

            # The example raised an exception:  check if it was expected.
            else:
                if check(example.want, got, self.optionflags):
                    outcome = SUCCESS

            # Report the outcome.
            if outcome is SUCCESS:
                if not quiet:
                    self.report_success(out, test, example, got)
            elif outcome is FAILURE:
                if not quiet:
                    self.report_failure(out, test, example, got)
                failures += 1
            elif outcome is BOOM:
                if not quiet:
                    self.report_unexpected_exception(out, test, example, exception)
                failures += 1
            else:
                assert False, ("unknown outcome", outcome)

            if failures and self.optionflags & FAIL_FAST:
                break

        # Restore the option flags (in case they were modified)
        self.optionflags = original_optionflags

        # Record and return the number of failures and tries.
        self.__record_outcome(test, failures, tries)
        return TestResults(failures, tries)

    def __record_outcome(self, test, f, t):
        """
        Record the fact that the given DocTest (`test`) generated `f`
        failures out of `t` tried examples.
        """
        f2, t2 = self._name2ft.get(test.name, (0, 0))
        self._name2ft[test.name] = (f + f2, t + t2)
        self.failures += f
        self.tries += t

    def run(self, test, compileflags=None, out=None, clear_globs=True):
        """
        Run the examples in `test`, and display the results using the
        writer function `out`.

        The examples are run in the namespace `test.globs`.  If
        `clear_globs` is true (the default), then this namespace will
        be cleared after the test runs, to help with garbage
        collection.  If you would like to examine the namespace after
        the test completes, then use `clear_globs=False`.

        `compileflags` gives the set of flags that should be used by
        the Python compiler when running the examples.  If not
        specified, then it will default to the set of future-import
        flags that apply to `globs`.

        The output of each example is checked using
        `DocTestRunner.check_output`, and the results are formatted by
        the `DocTestRunner.report_*` methods.
        """
        self.test = test

        if compileflags is None:
            compileflags = _extract_future_flags(test.globs)

        save_stdout = sys.stdout
        if out is None:
            encoding = save_stdout.encoding
            if encoding is None or encoding.lower() == "utf-8":
                out = save_stdout.write
            else:
                # Use backslashreplace error handling on write
                def out(s):
                    s = str(s.encode(encoding, "backslashreplace"), encoding)
                    save_stdout.write(s)

        sys.stdout = self._fakeout

        # Patch pdb.set_trace to restore sys.stdout during interactive
        # debugging (so it's not still redirected to self._fakeout).
        # Note that the interactive output will go to *our*
        # save_stdout, even if that's not the real sys.stdout; this
        # allows us to write test cases for the set_trace behavior.
        save_trace = sys.gettrace()
        save_set_trace = pdb.set_trace
        self.debugger = _OutputRedirectingPdb(save_stdout)
        self.debugger.reset()
        pdb.set_trace = self.debugger.set_trace

        # Patch linecache.getlines, so we can see the example's source
        # when we're inside the debugger.
        self.save_linecache_getlines = linecache.getlines
        linecache.getlines = self.__patched_linecache_getlines

        # Make sure sys.displayhook just prints the value to stdout
        save_displayhook = sys.displayhook
        sys.displayhook = sys.__displayhook__

        try:
            return self.__run(test, compileflags, out)
        finally:
            sys.stdout = save_stdout
            pdb.set_trace = save_set_trace
            sys.settrace(save_trace)
            linecache.getlines = self.save_linecache_getlines
            sys.displayhook = save_displayhook
            if clear_globs:
                test.globs.clear()
                try:
                    import builtins

                    builtins._ = None
                except ImportError:
                    pass


master = None


def testfile(
    filename,
    module_relative=True,
    name=None,
    package=None,
    globs=None,
    verbose=None,
    report=True,
    optionflags=0,
    extraglobs=None,
    raise_on_error=False,
    parser=ScriptDocTestParser(),
    encoding=None,
        base_path = None,
):
    """
    Test examples in the given file.  Return (#failures, #tests).

    Optional keyword arg "module_relative" specifies how filenames
    should be interpreted:

      - If "module_relative" is True (the default), then "filename"
         specifies a module-relative path.  By default, this path is
         relative to the calling module's directory; but if the
         "package" argument is specified, then it is relative to that
         package.  To ensure os-independence, "filename" should use
         "/" characters to separate path segments, and should not
         be an absolute path (i.e., it may not begin with "/").

      - If "module_relative" is False, then "filename" specifies an
        os-specific path.  The path may be absolute or relative (to
        the current working directory).

    Optional keyword arg "name" gives the name of the test; by default
    use the file's basename.

    Optional keyword argument "package" is a Python package or the
    name of a Python package whose directory should be used as the
    base directory for a module relative filename.  If no package is
    specified, then the calling module's directory is used as the base
    directory for module relative filenames.  It is an error to
    specify "package" if "module_relative" is False.

    Optional keyword arg "globs" gives a dict to be used as the globals
    when executing examples; by default, use {}.  A copy of this dict
    is actually used for each docstring, so that each docstring's
    examples start with a clean slate.

    Optional keyword arg "extraglobs" gives a dictionary that should be
    merged into the globals that are used to execute examples.  By
    default, no extra globals are used.

    Optional keyword arg "verbose" prints lots of stuff if true, prints
    only failures if false; by default, it's true iff "-v" is in sys.argv.

    Optional keyword arg "report" prints a summary at the end when true,
    else prints nothing at the end.  In verbose mode, the summary is
    detailed, else very brief (in fact, empty if all tests passed).

    Optional keyword arg "optionflags" or's together module constants,
    and defaults to 0.  Possible values (see the docs for details):

        DONT_ACCEPT_TRUE_FOR_1
        DONT_ACCEPT_BLANKLINE
        NORMALIZE_WHITESPACE
        ELLIPSIS
        SKIP
        IGNORE_EXCEPTION_DETAIL
        REPORT_UDIFF
        REPORT_CDIFF
        REPORT_NDIFF
        REPORT_ONLY_FIRST_FAILURE

    Optional keyword arg "raise_on_error" raises an exception on the
    first unexpected exception or failure. This allows failures to be
    post-mortem debugged.

    Optional keyword arg "parser" specifies a DocTestParser (or
    subclass) that should be used to extract tests from the files.

    Optional keyword arg "encoding" specifies an encoding that should
    be used to convert the file to unicode.

    Advanced tomfoolery:  testmod runs methods of a local instance of
    class doctest.Tester, then merges the results into (or creates)
    global Tester instance doctest.master.  Methods of doctest.master
    can be called directly too, if you want to do something unusual.
    Passing report=0 to testmod is especially useful then, to delay
    displaying a summary.  Invoke doctest.master.summarize(verbose)
    when you're done fiddling.
    """
    global master

    if package and not module_relative:
        raise ValueError("Package may only be specified for module-" "relative paths.")

    # Relativize the path
    try:
        text, filename = _load_testfile(
            filename, package, module_relative, encoding or "utf-8"
        )
    except TypeError:
        text, filename = _load_testfile(filename, package, module_relative)

    # If no name was given, then use the file's name.
    if name is None:
        name = os.path.basename(filename)

    # Assemble the globals.
    if globs is None:
        globs = {}
    else:
        globs = globs.copy()
    if extraglobs is not None:
        globs.update(extraglobs)
    if "__name__" not in globs:
        globs["__name__"] = "__main__"

    runner = ScriptDocTestRunner(verbose=verbose, optionflags=optionflags, base_path=base_path)

    # Read the file, convert it to a test, and run it.
    test = parser.get_doctest(text, globs, name, filename, 0)
    runner.run(test)

    if report:
        runner.summarize()

    if master is None:
        master = runner
    else:
        master.merge(runner)

    return TestResults(runner.failures, runner.tries)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="")
    parser.add_argument("filename")
    parser.add_argument("--base_path")
    parser.add_argument("--module_relative", action="store_true", default=False)
    parser.add_argument("--name", default=None)
    parser.add_argument("--package", default=None)
    parser.add_argument("--globs", default=None)
    parser.add_argument("--verbose", default=None)
    parser.add_argument("--report", action="store_false", default=True)
    parser.add_argument("--optionflags", type=int, default=(doctest.ELLIPSIS | CHANGE_DIRECTORY))
    parser.add_argument("--extraglobs", default=None)
    parser.add_argument("--raise_on_error", action="store_true", default=False)
    parser.add_argument("--parser", default=ScriptDocTestParser())
    parser.add_argument("--encoding", default=None)
    args = parser.parse_args()
    results = testfile(
        filename=args.filename,
        module_relative=args.module_relative,
        name=args.name,
        package=args.package,
        globs=args.globs,
        verbose=args.verbose,
        report=args.report,
        optionflags=args.optionflags,
        extraglobs=args.extraglobs,
        raise_on_error=args.raise_on_error,
        parser=args.parser,
        encoding=args.encoding,
        base_path=args.base_path,
    )
    if results.failed:
        sys.exit(1)
