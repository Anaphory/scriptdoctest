from scriptdoctest import *

files = """ Let's create a file like this::

    $ touch file
and now see it exists ::

    $ ls
    file
We can, of course, have multiple commands in one example block. ::

    $ touch new_file
    $ ls
    file
    new_file
They can even be separated by blank lines. ::

    $ ls
    file
    new_file

    $ rm new_file
We can also create a file by content.

    ::
 
        File 1
    -- other_file

This will then also show up in `ls` ::

    $ ls
    file
    other_file
and it's content will be exactly as specified. (In fact, we explicitly
test that the content survives a round trip through writing with
python and reading with `cat`, just in case.) ::

    $ cat other_file
    File 1
There is currently a third way to create a file, which is abusing cat,
but it may change soon. It involves using the doctest directive
`CREATE_FILE_BEFORE_TEST` and telling `cat` what it *should* output,
so that it will output precisely that. I am not fine with the syntax
and name of the directive yet. ::

    $ cat abused_file #doctest: +CREATE_FILE_BEFORE_TEST
        File 3
    -- other_file
Subdirectories are a separate matter. We should be able to create them::

    $ mkdir test
get into them::

    $ cd test #doctest: +CHANGE_DIRECTORY
See there's nothing in there (of course, it's a new empty directory!) ::

    $ ls
and step back out::

    $ cd .. #doctest: +CHANGE_DIRECTORY
    $ ls
    abused_file
    file
    other_file
    test
Note that `cd`s and environmental variables are in general
non-persistent, but you can make a `cd` with a spelled-out path (no
variable expansions, backticks etc.) stick by setting the
CHANGE_DIRECTORY doctest directive.
"""

print([m.groupdict() for m in 
    re.compile(r'''(
        ^(?P<preindent> [ ]*) ::\n
        (?P<options>(
            ([ ]*\n)|
            (?P=preindent)[#] .*\n)*)
        (?P<content>
            ((?P<fullindent> (?P=preindent)[ ]+).*\n)*)
        )''', re.MULTILINE | re.VERBOSE).finditer(files)])


p = ScriptDocTestParser()
for part in p.parse(files):
    print("="*20)
    try:
        print("$", part.source)
        print(part.want)
    except AttributeError:
        print(part)
    
testfile(__file__)




