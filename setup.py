#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright (c) 2011 Sylvain Prat. This program is open-source software,
# and may be redistributed under the terms of the MIT license. See the
# LICENSE.txt file in this distribution for details.

import os.path
from setuptools import setup
from yaak.inject import __version__ as version


def read(*rnames):
    return open(os.path.join(os.getcwd(), *rnames)).read()


desc = """A dependency injection framework for your python applications"""

long_description = (
    read('README.txt') +
    '\n' +
    read('CHANGES.txt')
)

# FIXME: remember to add a download url
# FIXME: setup an API documentation
setup(
    name='yaak.inject',
    version=version,
    author='Sylvain Prat',
    author_email='sylvain.prat+yaak.inject@gmail.com',
    description=desc,
    long_description=long_description,
    #download_url='...',
    license='MIT License',
    keywords='dependency, injection, inject',
    url='http://bitbucket.org/sprat/yaak.inject',
    packages=['yaak'],
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
