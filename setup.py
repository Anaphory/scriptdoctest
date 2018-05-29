#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name="scriptdoctest",
    version="0.2",
    description="Verify interactive shell session examples",
    author="Gereon Kaiping",
    author_email="anaphory@yahoo.de",
    license="MIT",
    modules=["scripttest.py", "scriptdoctest.py"],
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
)
