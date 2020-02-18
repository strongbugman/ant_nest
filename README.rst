========
AntNest
========

.. image:: https://img.shields.io/pypi/v/ant_nest.svg
   :target: https://pypi.python.org/pypi/ant_nest

.. image:: https://img.shields.io/travis/strongbugman/ant_nest/master.svg
   :target: https://travis-ci.org/strongbugman/ant_nest

.. image:: https://codecov.io/gh/strongbugman/ant_nest/branch/master/graph/badge.svg
  :target: https://codecov.io/gh/strongbugman/ant_nest

Overview
========

AntNest is a simple, clear and fast Web Crawler framework build on python3.6+, powered by asyncio.
It has only 600+ lines core code now(thanks powerful lib like aiohttp, lxml and other else).

Features
========

* Useful http client out of box
* Easy things(request, response and item) pipelines(in async or not)
* Easy Item extractor, define data detail(by xpath, jpath or regex) and extract from html, json or strings.
* Easy work flow

Install
=======
::

    pip install ant_nest

Usage
=====

Create one demo project::

    >>> ant_nest -c examples

Then we get a project::

    drwxr-xr-x   5 bruce  staff  160 Jun 30 18:24 ants
    -rw-r--r--   1 bruce  staff  208 Jun 26 22:59 settings.py

Presume we want to get hot repos from github, let`s create "examples/ants/example2.py"::

    from yarl import URL
    from ant_nest.ant import Ant
    from ant_nest.pipelines import ItemFieldReplacePipeline
    from ant_nest.things import ItemExtractor


    class GithubAnt(Ant):
        """Crawl trending repositories from github"""

        item_pipelines = [
            ItemFieldReplacePipeline(
                ("meta_content", "star", "fork"), excess_chars=("\r", "\n", "\t", "  ")
            )
        ]
        concurrent_limit = 1  # save the website`s and your bandwidth!

        def __init__(self):
            super().__init__()
            self.item_extractor = ItemExtractor(dict)
            self.item_extractor.add_extractor(
                "title", lambda x: x.html_element.xpath("//h1/strong/a/text()")[0]
            )
            self.item_extractor.add_extractor(
                "author", lambda x: x.html_element.xpath("//h1/span/a/text()")[0]
            )
            self.item_extractor.add_extractor(
                "meta_content",
                lambda x: "".join(
                    x.html_element.xpath(
                        '//div[@class="repository-content "]/div[2]//text()'
                    )
                ),
            )
            self.item_extractor.add_extractor(
                "star",
                lambda x: x.html_element.xpath(
                    '//a[@class="social-count js-social-count"]/text()'
                )[0],
            )
            self.item_extractor.add_extractor(
                "fork",
                lambda x: x.html_element.xpath('//a[@class="social-count"]/text()')[0],
            )
            self.item_extractor.add_extractor("origin_url", lambda x: str(x.url))

        async def crawl_repo(self, url):
            """Crawl information from one repo"""
            response = await self.request(url)
            # extract item from response
            item = self.item_extractor.extract(response)
            item["origin_url"] = response.url

            await self.collect(item)  # let item go through pipelines(be cleaned)
            self.logger.info("*" * 70 + "I got one hot repo!\n" + str(item))

        async def run(self):
            """App entrance, our play ground"""
            response = await self.request("https://github.com/explore")
            for url in response.html_element.xpath(
                "/html/body/div[4]/main/div[2]/div/div[2]/div[1]/article/div/div[1]/h1/a[2]/"
                "@href"
            ):
                # crawl many repos with our coroutines pool
                self.schedule_task(self.crawl_repo(response.url.join(URL(url))))
            self.logger.info("Waiting...")


Then we can list all ants we defined (in "examples") ::

    >>> $ant_nest -l
    ants.example2.GithubAnt

Run it! (without debug log)::

    >>> ant_nest -a ants.example2.GithubAnt
    INFO:GithubAnt:Opening
    INFO:GithubAnt:Waiting...
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'app-ideas', 'author': 'florinpop17', 'meta_content': 'A Collection of application ideas which can be used to improve your coding skills.', 'star': '11.7k', 'fork': '500', 'origin_url': URL('https://github.com/florinpop17/app-ideas')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'Carbon', 'author': 'briannesbitt', 'meta_content': 'A simple PHP API extension for DateTime.https://carbon.nesbot.com/', 'star': '14k', 'fork': '249', 'origin_url': URL('https://github.com/briannesbitt/Carbon')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'org-roam', 'author': 'jethrokuan', 'meta_content': 'Rudimentary Roam replica with Org-modehttps://org-roam.readthedocs.io/en/la…', 'star': '261', 'fork': '27', 'origin_url': URL('https://github.com/jethrokuan/org-roam')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'joplin', 'author': 'laurent22', 'meta_content': 'Joplin - an open source note taking and to-do application with synchronization capabilities for Windows, macOS, Linux, Android and iOS. Forum: https://discourse.joplinapp.org/https://joplinapp.org', 'star': '13k', 'fork': '335', 'origin_url': URL('https://github.com/laurent22/joplin')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'snoop', 'author': 'snooppr', 'meta_content': 'Snoop — инструмент разведки на основе открытых данных', 'star': '281', 'fork': '9', 'origin_url': URL('https://github.com/snooppr/snoop')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': '1on1-questions', 'author': 'VGraupera', 'meta_content': 'Mega list of 1 on 1 meeting questions compiled from a variety to sources', 'star': '4k', 'fork': '93', 'origin_url': URL('https://github.com/VGraupera/1on1-questions')}
    INFO:GithubAnt:Get 8 Request in total with 8/60s rate
    INFO:GithubAnt:Get 7 Response in total with 7/60s rate
    INFO:GithubAnt:Get 6 dict in total with 6/60s rate
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'python-small-examples', 'author': 'jackzhenguo', 'meta_content': 'Python有趣的小例子一网打尽。Python基础、Python坑点、Python字符串和正则、Python绘图、Python日期和文件、Web开发、数据科学、机器学习、深度2.4k', 'fork': '102', 'origin_url': URL('https://github.com/jackzhenguo/python-small-examples')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'system-design-primer', 'author': 'donnemartin', 'meta_content': 'Learn how to design large-scale systems. Prep for the system design interview. Includes Anki flashcards.', 'star': '83.2k', 'fork': '4.4k', 'origin_url': URL('https://github.com/donnemartin/system-design-primer')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'awesome-scalability', 'author': 'binhnguyennus', 'meta_content': 'The Patterns of Scalable, Reliable, and Performant Large-Scale Systemshttp://awesome-scalability.com/', 'star': '24.5k', 'fork': '1.4k', 'origin_url': URL('https://github.com/binhnguyennus/awesome-scalability')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'gdb-frontend', 'author': 'rohanrhu', 'meta_content': '☕ GDBFrontend is an easy, flexible and extensionable gui debugger.https://oguzhaneroglu.com/projects/gd…', 'star': '716', 'fork': '14', 'origin_url': URL('https://github.com/rohanrhu/gdb-frontend')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'Complete-Python-3-Bootcamp', 'author': 'Pierian-Data', 'meta_content': 'Course Files for Complete Python 3 Bootcamp Course on Udemy', 'star': '8.1k', 'fork': '1.8k', 'origin_url': URL('https://github.com/Pierian-Data/Complete-Python-3-Bootcamp')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'leon', 'author': 'leon-ai', 'meta_content': '\U0001f9e0 Leon is your open-source personal assistant.https://getleon.ai', 'star': '6.3k', 'fork': '147', 'origin_url': URL('https://github.com/leon-ai/leon')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'esbuild', 'author': 'evanw', 'meta_content': 'An extremely fast JavaScript bundler and minifier', 'star': '2.3k', 'fork': '38', 'origin_url': URL('https://github.com/evanw/esbuild')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'wearable-microphone-jamming', 'author': 'y-x-c', 'meta_content': 'Repository for our paper Wearable Microphone Jamminghttp://sandlab.cs.uchicago.edu/jammer/', 'star': '138', 'fork': '10', 'origin_url': URL('https://github.com/y-x-c/wearable-microphone-jamming')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'efcore', 'author': 'dotnet', 'meta_content': 'EF Core is a modern object-database mapper for .NET. It supports LINQ queries, change tracking, updates, and schema migrations.https://docs.microsoft.com/ef/core/', 'star': '8.7k', 'fork': '965', 'origin_url': URL('https://github.com/dotnet/efcore')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'playwright', 'author': 'microsoft', 'meta_content': 'Node library to automate Chromium, Firefox and WebKit with a single APIhttps://www.npmjs.com/package/playwright', 'star': '9k', 'fork': '92', 'origin_url': URL('https://github.com/microsoft/playwright')}
    INFO:GithubAnt:Get 18 Request in total with 10/60s rate
    INFO:GithubAnt:Get 17 Response in total with 10/60s rate
    INFO:GithubAnt:Get 16 dict in total with 10/60s rate
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'degoogle', 'author': 'tycrek', 'meta_content': 'A huge list of alternatives to Google products. Privacy tips, tricks, and links.https://degoogle.jmoore.dev', 'star': '2k', 'fork': '50', 'origin_url': URL('https://github.com/tycrek/degoogle')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'sherlock', 'author': 'sherlock-project', 'meta_content': '🔎 Hunt down social media accounts by username across social networkshttp://sherlock-project.github.io', 'star': '10.4k', 'fork': '207', 'origin_url': URL('https://github.com/sherlock-project/sherlock')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'the-art-of-command-line', 'author': 'jlevy', 'meta_content': 'Master the command line, in one page', 'star': '68.9k', 'fork': '2.2k', 'origin_url': URL('https://github.com/jlevy/the-art-of-command-line')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'freespeech', 'author': 'Merkie', 'meta_content': 'A free program designed to help the non-verbal.', 'star': '168', 'fork': '20', 'origin_url': URL('https://github.com/Merkie/freespeech')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'awesome-pentest', 'author': 'enaqx', 'meta_content': 'A collection of awesome penetration testing resources, tools and other shiny things', 'star': '11.4k', 'fork': '1k', 'origin_url': URL('https://github.com/enaqx/awesome-pentest')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'trax', 'author': 'google', 'meta_content': 'Trax — your path to advanced deep learning', 'star': '2.7k', 'fork': '90', 'origin_url': URL('https://github.com/google/trax')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'introtodeeplearning', 'author': 'aamini', 'meta_content': 'Lab Materials for MIT 6.S191: Introduction to Deep Learning', 'star': '1.6k', 'fork': '116', 'origin_url': URL('https://github.com/aamini/introtodeeplearning')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'CleanArchitecture', 'author': 'ardalis', 'meta_content': 'A starting point for Clean Architecture with ASP.NET Core', 'star': '3.8k', 'fork': '300', 'origin_url': URL('https://github.com/ardalis/CleanArchitecture')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': '3y', 'author': 'ZhongFuCheng3y', 'meta_content': '📓从Java基础、JavaWeb基础到常用的框架再到面试题都有完整的教程，几乎涵盖了Java后端必备的知识点', 'star': '5.1k', 'fork': '285', 'origin_url': URL('https://github.com/ZhongFuCheng3y/3y')}
    INFO:GithubAnt:Closed
    INFO:GithubAnt:Get 26 Request in total
    INFO:GithubAnt:Get 26 Response in total
    INFO:GithubAnt:Get 25 dict in total
    INFO:GithubAnt:Run GithubAnt in 180.234251 seconds


About Item
==========

We use dict to store one item in examples, actually it support many way:
dict, normal class, atrrs's class, data class and ORM class, it depend on your need and choice.

Examples
========

You can get some example in "./examples"

Defect
======

* Complex exception handle

one coroutine's exception will break await chain especially in a loop, unless we handle it by hand. eg::

    for cor in self.as_completed((self.crawl(url) for url in self.urls)):
        try:
            await cor
        except Exception:  # may raise many exception in a await chain
            pass

but we can use "self.as_completed_with_async" now, eg::

    async fo result in self.as_completed_with_async(
    self.crawl(url) for url in self.urls, raise_exception=False):
        # exception in "self.crawl(url)" will be passed and logged automatic
        self.handle(result)

* High memory usage

It`s a "feature" that asyncio eat large memory especially with high concurrent IO, we can set a
concurrent limit("connection_limit" or "concurrent_limit") simply, but it`s complex to get the balance between performance and limit.


Coding style
============

Follow "Flake8", Format by "Black", typing check by "MyPy", sea Makefile for more detail.


Todo
====

[*] Log system
[*] Nest item extractor
[ ] Docs
