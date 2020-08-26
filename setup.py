#!/usr/bin/env python3
from setuptools import setup, find_packages
import re

with open("ant_nest/__init__.py", "rt", encoding="utf8") as f:
    match = re.search(r"__version__ = \"(.*?)\"", f.read())
    if match:
        version = match.group(1)
    else:
        raise Exception("Version not found!")

requires = [
    "httpx>=0.14.0",
    "tenacity>=4.8.0",
    "ujson>=1.3.4",
    "aiofiles>=0.3.1",
    "typing_extensions>=3.6",
    "IPython>=7.0",
]
tests_requires = [
    "pytest>=3.3.1",
    "pytest-asyncio>=0.8.0",
    "pytest-cov>=2.5.1",
    "pytest-mock>=2.0.0",
    "jpath>=1.6",
    "beautifulsoup4",
    "lxml>3.7.0",
]
setup_requires = ["pytest-runner>=3.0"]

setup(
    name="ant_nest",
    version=version,
    url="https://github.com/strongbugman/ant_nest",
    description="A simple and clear Web Crawler framework build on python3.6+ "
    "with async",
    long_description=open("README.rst").read(),
    author="Bruce Wu",
    author_email="strongbugman@gmail.com",
    license="LGPL",
    classifiers=[
        "Environment :: Console",
        "Programming Language :: Python :: 3.6",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    packages=find_packages(exclude=("tests", "tests.*")),
    install_requires=requires,
    entry_points={"console_scripts": ["ant_nest = ant_nest.cli:main"]},
    setup_requires=setup_requires,
    tests_require=tests_requires,
)
