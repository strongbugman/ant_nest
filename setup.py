#!/usr/bin/env python3
from setuptools import setup, find_packages
import re


with open('ant_nest/__init__.py', 'rt', encoding='utf8') as f:
    version = re.search(r'__version__ = \'(.*?)\'', f.read()).group(1)


requires = ['aiohttp>=2.3.2', 'lxml>=3.7.0',
            'aiomysql>=0.0.11', 'PyMySQL>=0.7.11', 'aioredis>=1.0.0',
            'jpath>=1.5', 'aiosmtplib>=1.0.2', 'tenacity>=4.8.0', 'simplejson>=3.5.0',
            'aiofiles>=0.3.1']
tests_require = ['pytest>=3.3.1', 'pytest-asyncio>=0.8.0', 'pytest-cov>=2.5.1']
setup_require = ['pytest-runner>=3.0']


setup(
    name="ant_nest",
    version=version,
    url='https://github.com/strongbugman/ant_nest',
    description='A simple and clear Web Crawler framework build on python3.6+ with async',
    long_description=open('README.rst').read(),
    author='Bruce Wu',
    author_email='1wumingyu1@gmail.com',
    license='LGPL',
    classifiers=[
        'Environment :: Console',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    packages=find_packages(exclude=('tests', 'tests.*')),
    install_requires=requires,
    entry_points={
        'console_scripts': ['ant_nest = ant_nest.cli:main']
    },
    setup_requires=setup_require,
    tests_require=tests_require
)
