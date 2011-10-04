#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright (c) 2011 Sylvain Prat. This program is open-source software,
# and may be redistributed under the terms of the MIT license. See the
# LICENSE file in this distribution for details.

import os.path
from setuptools import setup
from yaak.inject import __version__ as version


def read_file(filename):
    current_dir = os.path.dirname(__file__)
    return open(os.path.join(current_dir, filename)).read()


desc = """yaak.inject provides dependency injection to your applications"""


setup(
    name='yaak.inject',
    version=version,
    author='Sylvain Prat',
    author_email='sylvain.prat+yaak.inject@gmail.com',
    description=desc,
    long_description=read_file('README'),
    license='MIT License',
    keywords='dependency, injection, inject',
    url='http://bitbucket.org/sprat/yaak.inject',
    packages=['yaak'],
    namespace_packages=['yaak'],
    test_suite='yaak.tests',
    classifiers=[
        'Development Status :: 1 - Planning',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],
    platforms='any'
)
