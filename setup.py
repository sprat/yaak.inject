#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright (c) 2011-2012 Sylvain Prat. This program is open-source software,
# and may be redistributed under the terms of the MIT license. See the
# LICENSE file in this distribution for details.

import os
import re

from setuptools import setup, find_packages


def read(*path_parts):
    here = os.path.dirname(__file__)
    return open(os.path.join(here, *path_parts)).read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")



desc = """A dependency injection framework for your python applications"""
long_desc = '\n'.join(read(f) for f in ('README', 'CHANGES'))


setup(
    name='yaak.inject',
    version=find_version('yaak', 'inject.py'),
    author='Sylvain Prat',
    author_email='sylvain.prat+yaak.inject@gmail.com',
    description=desc,
    long_description=long_desc,
    license='MIT License',
    keywords='dependency, injection, inject',
    url='http://bitbucket.org/sprat/yaak.inject',
    download_url='http://pypi.python.org/pypi/yaak.inject',
    packages=find_packages(),
    namespace_packages=['yaak'],
    test_suite='yaak.tests',
    extras_require={'doc': ('Sphinx', 'Sphinx-PyPI-upload',)},
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Environment :: Win32 (MS Windows)',
        'Environment :: X11 Applications',
        'Environment :: MacOS X',
        'Environment :: Other Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
    ],
    platforms='any'
)
