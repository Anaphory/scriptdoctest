from scriptdoctest import *

files = """ Let's create a file like this::

    $ touch file

and now see it exists ::

    $ ls
    file

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
and name of the directive yet.

    $ cat abused_file #doctest: +CREATE_FILE_BEFORE_TEST
    File 3
    -- other_file

Subdirectories are a separate matter. We should be able to create them::

    $ mkdir test

get into them::

    $ cd test

be in there::

    $ ls

and step back out::

    $ cd ..
    $ ls
    abused_file
    file
    other_file
"""


p = ScriptDocTestParser()
for part in p.parse(files):
    print("="*20)
    try:
        print("$", part.source)
        print(part.want)
    except AttributeError:
        pass
    
testfile(__file__)
