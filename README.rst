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

* Things(request, response and item) can though pipelines(in async or not)
* Item extractor,  it`s easy to define and extract(by xpath, jpath or regex) one item we want from html, json or strings.
* Custom "ensure_future" and "as_completed" api provide a easy work flow

Install
=======
::

    pip install ant_nest

Usage
=====

Create one demo project by cli::

    >>> ant_nest -c examples

Then we have a project::

    drwxr-xr-x   5 bruce  staff  160 Jun 30 18:24 ants
    -rw-r--r--   1 bruce  staff  208 Jun 26 22:59 settings.py

Presume we want to get hot repos from github, let`s create "examples/ants/example2.py"::

    from ant_nest import *
    from yarl import URL


    class GithubAnt(Ant):
        """Crawl trending repositories from github"""
        item_pipelines = [
            ItemFieldReplacePipeline(
                ('meta_content', 'star', 'fork'),
                excess_chars=('\r', '\n', '\t', '  '))
        ]
        pool_limit = 1  # save the website`s and your bandwidth!

        def __init__(self):
            super().__init__()
            self.item_extractor = ItemExtractor(dict)
            self.item_extractor.add_xpath('title', '//h1/strong/a/text()')
            self.item_extractor.add_xpath('author', '//h1/span/a/text()')
            self.item_extractor.add_xpath(
                'meta_content',
                '//div[@class="repository-meta-content col-11 mb-1"]//text()',
                extract_type=ItemExtractor.extract_with_join_all)
            self.item_extractor.add_xpath(
                'star', '//a[@class="social-count js-social-count"]/text()')
            self.item_extractor.add_xpath(
                'fork', '//a[@class="social-count"]/text()')

        async def crawl_repo(self, url):
            """Crawl information from one repo"""
            response = await self.request(url)
            # extract item from response
            item = self.item_extractor.extract(response)
            item['origin_url'] = response.url

            await self.collect(item)  # let item go through pipelines(be cleaned)
            self.logger.info('*' * 70 + 'I got one hot repo!\n' + str(item))

        async def run(self):
            """App entrance, our play ground"""
            response = await self.request('https://github.com/explore')
            for url in response.html_element.xpath(
                    '/html/body/div[4]/div[2]/div/div[2]/div[1]/article//h1/a[2]/'
                    '@href'):
                # crawl many repos with our coroutines pool
                self.pool.schedule_coroutine(
                    self.crawl_repo(response.url.join(URL(url))))
            self.logger.info('Waiting...')

Then we can list all ants we defined in a console(in "examples") ::

    >>> $ant_nest -l
    ants.example2.GithubAnt

Run it! (without debug log)::

    >>> ant_nest -a ants.example2.GithubAnt
    INFO:GithubAnt:Opening
    INFO:GithubAnt:Waiting...
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'NLP-progress', 'author': 'sebastianruder', 'meta_content': 'Repository to track the progress in Natural Language Processing (NLP), including the datasets and the current state-of-the-art for the most common NLP tasks.', 'star': '3,743', 'fork': '327', 'origin_url': URL('https://github.com/sebastianruder/NLP-progress')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'material-dashboard', 'author': 'creativetimofficial', 'meta_content': 'Material Dashboard - Open Source Bootstrap 4 Material Design Adminhttps://demos.creative-tim.com/materi…', 'star': '6,032', 'fork': '187', 'origin_url': URL('https://github.com/creativetimofficial/material-dashboard')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'mkcert', 'author': 'FiloSottile', 'meta_content': "A simple zero-config tool to make locally-trusted development certificates with any names you'd like.", 'star': '2,311', 'fork': '60', 'origin_url': URL('https://github.com/FiloSottile/mkcert')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'pure-bash-bible', 'author': 'dylanaraps', 'meta_content': '📖 A collection of pure bash alternatives to external processes.', 'star': '6,385', 'fork': '210', 'origin_url': URL('https://github.com/dylanaraps/pure-bash-bible')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'flutter', 'author': 'flutter', 'meta_content': 'Flutter makes it easy and fast to build beautiful mobile apps.https://flutter.io', 'star': '30,579', 'fork': '1,337', 'origin_url': URL('https://github.com/flutter/flutter')}
    INFO:GithubAnt:**********************************************************************I got one hot repo!
    {'title': 'Java-Interview', 'author': 'crossoverJie', 'meta_content': '👨\u200d🎓 Java related : basic, concurrent, algorithm https://crossoverjie.top/categories/J…', 'star': '4,687', 'fork': '409', 'origin_url': URL('https://github.com/crossoverJie/Java-Interview')}
    INFO:GithubAnt:Closed
    INFO:GithubAnt:Get 7 Request in total
    INFO:GithubAnt:Get 7 Response in total
    INFO:GithubAnt:Get 6 dict in total
    INFO:GithubAnt:Run GithubAnt in 18.157656 seconds

Defect
======

* Complex exception handle

one coroutine`s exception will break await chain especially in a loop unless we handle it by
hand. eg::

    for cor in self.pool.as_completed((self.crawl(url) for url in self.urls)):
        try:
            await cor
        except Exception:  # may raise many exception in a await chain
            pass

but we can use "queen.as_completed_with_async" now, eg::

    async fo result in self.pool.as_completed_with_async(self.crawl(url) for ufl in self.urls):
        # exception in "self.crawl(url)" will be passed and logged automatic
        self.handle(result)

* High memory usage

It`s a "feature" that asyncio eat large memory especially with high concurrent IO, one simple solution is set a
concurrent limit, but it`s complex to get the balance between performance and limit.

Todo
====

[ ] Docs
[ ] Log system
