#!/usr/bin/env python3

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name="scriptdocdest",
    version="0.1",
    description="Verify interactive shell session examples",
    author="Gereon Kaiping",
    author_email="anaphory@yahoo.de",
    license="MIT",
    modules=["scripttest.py", "scriptdoctest.py"],
)
    
