from ant_nest import *
from yarl import URL


class GithubAnt(Ant):
    """Crawl trending repositories from github"""

    item_pipelines = [
        ItemFieldReplacePipeline(
            ("meta_content", "star", "fork"),
            excess_chars=("\r", "\n", "\t", "  "),
        )
    ]
    concurrent_limit = 1  # save the website`s and your bandwidth!

    async def crawl_repo(self, url):
        """Crawl information from one repo"""
        response = await self.request(url)
        # extract item from response
        item = dict()
        item["title"] = ItemExtractor.extract_value(
            "xpath", "//h1/strong/a/text()", response
        )
        item["author"] = ItemExtractor.extract_value(
            "xpath", "//h1/span/a/text()", response
        )
        item["meta_content"] = ItemExtractor.extract_value(
            "xpath",
            '//div[@class="repository-content "]/div[2]//text()',
            response,
            extract_type=ItemExtractor.EXTRACT_WITH_JOIN_ALL,
            default="Not found!",
        )
        item["star"] = ItemExtractor.extract_value(
            "xpath",
            '//a[@class="social-count js-social-count"]/text()',
            response,
        )
        item["fork"] = ItemExtractor.extract_value(
            "xpath", '//a[@class="social-count"]/text()', response
        )
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
