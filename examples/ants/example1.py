from ant_nest.ant import Ant
from ant_nest.pipelines import ItemFieldReplacePipeline
from bs4 import BeautifulSoup
from lxml import html


class GithubAnt(Ant):
    """Crawl trending repositories from github"""

    item_pipelines = [
        ItemFieldReplacePipeline(
            ("meta_content", "star", "fork"), excess_chars=("\r", "\n", "\t", "  ")
        )
    ]

    async def crawl_repo(self, url):
        """Crawl information from one repo"""
        response = await self.request(url)
        # extract item from response
        item = dict()
        element = html.fromstring(response.text)
        item["title"] = element.xpath("//h1/strong/a/text()")[0]
        item["author"] = element.xpath("//h1/span/a/text()")[0]
        item["meta_content"] = "".join(
            element.xpath('//div[@class="repository-content "]/div[2]//text()')
        )
        item["star"] = element.xpath(
            '//a[@class="social-count js-social-count"]/text()'
        )[0]
        item["fork"] = element.xpath('//a[@class="social-count"]/text()')[0]
        item["origin_url"] = response.url

        await self.collect(item)  # let item go through pipelines(be cleaned)
        self.logger.info("*" * 70 + "I got one hot repo!\n" + str(item))

    async def run(self):
        """App entrance, our play ground"""
        response = await self.request("https://github.com/explore")
        soup = BeautifulSoup(response.text, "html.parser")
        urls = set()
        for node in soup.main.find_all(
            "a", **{"data-ga-click": "Explore, go to repository, location:explore feed"}
        ):
            urls.add(response.url.join(node["href"]))
        for url in urls:
            self.pool.spawn(self.crawl_repo(url))
        self.logger.info("Waiting...")
