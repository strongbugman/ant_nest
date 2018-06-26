from ant_nest import *


class PythonNewsAnt(Ant):
    """Crawl last python news from python.org!"""
    pool_limit = 1  # save website`s and your bandwidth!
    request_retries = 0

    async def crawl_news(self, url):
        """Crawl story from one url"""
        response = await self.request(url)
        # extract item from response
        item = dict()
        item['title'] = extract_value_by_xpath(
            '//h3[@class="post-title entry-title"]/text()',
            response, ignore_exception=False)  # this page must have one title!
        item['content'] = extract_value_by_xpath(
            '//div[@class="post-body entry-content"//text()',
            response, extract_type=ItemExtractor.extract_with_join_all,
            default='Not found!')
        item['date'] = extract_value_by_xpath(
            '//h2[@class="date-header"/span/text()', response)
        item['origin_url'] = response.url

        self.logger.info('I got one news!\n' + str(item))

    async def run(self):
        """App entrance, our play ground"""
        response = await self.request('https://www.python.org')
        # crawl many books in pool
        for url in response.html_element.xpath(
                '/html/body/div/div[3]/div/section/div[2]/div[1]/div/ul//a/@href'):
            self.pool.schedule_coroutine(self.crawl_news(url))
            break
