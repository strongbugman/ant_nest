from yarl import URL
from ant_nest.ant import Ant
from ant_nest.pipelines import ItemFieldReplacePipeline


class GithubAnt(Ant):
    """Crawl trending repositories from github"""

    item_pipelines = [
        ItemFieldReplacePipeline(
            ("meta_content", "star", "fork"), excess_chars=("\r", "\n", "\t", "  ")
        )
    ]
    concurrent_limit = 1  # save the website`s and your bandwidth!

    async def crawl_repo(self, url):
        """Crawl information from one repo"""
        response = await self.request(url)
        # extract item from response
        item = dict()
        item["title"] = response.html_element.xpath("//h1/strong/a/text()")[0]
        item["author"] = response.html_element.xpath("//h1/span/a/text()")[0]
        item["meta_content"] = "".join(
            response.html_element.xpath(
                '//div[@class="repository-content "]/div[2]//text()'
            )
        )
        item["star"] = response.html_element.xpath(
            '//a[@class="social-count js-social-count"]/text()'
        )[0]
        item["fork"] = response.html_element.xpath('//a[@class="social-count"]/text()')[
            0
        ]
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
