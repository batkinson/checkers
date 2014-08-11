#!/usr/bin/env python
from distutils.core import setup
import py2exe
import glob

setup(windows=["checkers.py"],
name='Checkers',
version='1.0',
description='Checkers Game',
author='Clare Richardson',
author_email='tech@girlstart.org',
url='www.girlstart.org/itgirl',
#py_modules=['mahjong','background','board','tile'],
data_files=[("images", glob.glob("images/*.*"))],
)