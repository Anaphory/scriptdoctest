#!/usr/bin/env python

import setuptools

setuptools.setup(
    name='scriptdoctest',
    version='0.3',
    description="""Helper to test interactive shell
        snippet examples in documentation""",
    long_description=open('README.rst').read(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Documentation',
        'Topic :: Software Development :: Testing',
        'Topic :: Software Development :: Documentation',
        'Topic :: System :: Shells',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3'],
    keywords='test doctest command line scripts tutorial',
    author='Gereon Kaiping',
    author_email='gereon.kaiping@gmail.com',
    url='https://github.com/Anaphory/scriptdoctest',
    license='MIT',
    package_dir={'': 'src'},
    py_modules=['scriptdoctest', 'scripttest'],
)
