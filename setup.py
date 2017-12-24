#!/usr/bin/env python3
from setuptools import setup, find_packages


requires = ['aiohttp==2.3.6', 'async-timeout==2.0.0', 'chardet==3.0.4', 'lxml==4.1.1', 'multidict==3.3.2',
            'py==1.5.2', 'pytest==3.3.1', 'pytest-asyncio==0.8.0', 'yarl==0.16.0', 'aiomysql==0.0.11', 'PyMySQL==0.7.11',
            'jpath==1.5', 'aiosmtplib==1.0.2', 'tenacity==4.8.0']


setup(
    name="ant_nest",
    version="0.22.0",
    url='https://github.com/6ugman/ant_nest',
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
