#!/usr/bin/env python3
from setuptools import setup, find_packages


requires =['aiohttp==2.3.2', 'async-timeout==2.0.0', 'chardet==3.0.4', 'lxml==4.1.1', 'multidict==3.3.2',
           'py==1.5.2', 'pytest==3.2.5', 'pytest-asyncio==0.8.0', 'yarl==0.13.0']


setup(
    name="ant_nest",
    version="0.12",
    url='https://github.com/YugWu/ant_nest',
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
)
