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

AntNest is a simple, clear and fast Web Crawler framework build on python3.6+,  powered by asyncio.

As a Scrapy user, I think scrapy provide many awesome features what I think AntNest should have too.This is some main
difference:

* Scrapy use callback way to write code while AntNest use coroutines
* Scrapy is stable and widely usage while AntNest is in early development
* AntNest has only 600+ lines core code now(thanks powerful lib like aiohttp, lxml and other else), and it works

Features
========

* Things(request, response and item) can though pipelines(in async or not)
* Item and item extractor,  it`s easy to define and extract(by xpath, jpath or regex) a validated(by field type) item
* Custom "ensure_future" and "as_completed" api provide a easy work flow

Install
=======
::

    pip install ant_nest

Usage
=====

Let`s take a look, create book.py first::

    from ant_nest import *

    # define a item structure we want to crawl
    class BookItem(Item):
        name = StringField()
        author = StringField(default='Li')
        content = StringField()
        origin_url = StringField()
        date = IntField(null=True)  # The filed is optional


    # define our ant
    class BookAnt(Ant):
        request_retry_delay = 10
        request_allow_redirects = False
        # the things(request, response, item) will pass through pipelines in order, pipelines can change or drop them
        item_pipelines = [ItemValidatePipeline(),
                          ItemMysqlInsertPipeline(settings.MYSQL_HOST, settings.MYSQL_PORT, settings.MYSQL_USER,
                                                  settings.MYSQL_PASSWORD, settings.MYSQL_DATABASE, 'book'),
                          ReportPipeline()]
        request_pipelines = [RequestDuplicateFilterPipeline(), RequestUserAgentPipeline(), ReportPipeline()]
        response_pipelines = [ResponseFilterErrorPipeline(), ReportPipeline()]


        # define ItemExtractor to extract item field by xpath from response(html source code)
        self.item_extractor = ItemExtractor(BookItem)
        self.item_extractor.add_regex('name', 'name=(\w+);')
        self.item_extractor.add_xpath('author', '/html/body/div[1]/div[@class="author"]/text()')
        self.item_extractor.add_xpath('content', '/html/body/div[2]/div[2]/div[2]//text()',
                                      ItemExtractor.join_all)

        # crawl book information
        async def crawl_book(self, url):
            # send request and wait for response
            response = await self.request(url)
            # extract item from response
            item = self.item_extractor.extract(response)
            item.origin_url = str(response.url)  # or item['origin_url'] = str(response.url)
            # wait "collect" coroutine, it will let item pass through "item_pipelines"
            await self.collect(item)

        # app entrance
        async def run(self):
            response = await self.request('https://fake_bookstore.com')
            # extract all book links by xpath ("html_element" is a HtmlElement object from lxml lib)
            urls = response.html_element.xpath('//a[@class="single_book"]/@href')
            # run "crawl_book" coroutines in concurrent
            for url in urls:
                # "pool.schedule_coroutine" is a function like "ensure_future" in "asyncio",
                # but it provide something else
                self.pool.schedule_coroutine(self.crawl_book(url), timeout=5)

Create a settings.py::

    import logging


    logging.basicConfig(level=logging.DEBUG)
    ANT_PACKAGES = ['book']

Then in a console::

    $ant_nest -a book.BookAnt

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

* Create "setting.py" from CLI
* Nested data(html and json) extractor, done
* Log system
