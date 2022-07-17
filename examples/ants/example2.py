from bs4 import BeautifulSoup
from lxml import html
from ant_nest.ant import Ant
from ant_nest.pipelines import ItemFieldReplacePipeline
from ant_nest.items import Extractor


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
        self.item_extractor = Extractor(dict)
        self.item_extractor.add_extractor(
            "title",
            lambda x: html.fromstring(x.text).xpath("/html/body/div[4]/div/main/div/div[1]/div/div/strong/a/text()")[0],
        )
        self.item_extractor.add_extractor(
            "author",
            lambda x: html.fromstring(x.text).xpath("/html/body/div[4]/div/main/div/div[1]/div/div/span[1]/a/text()")[0],
        )
        self.item_extractor.add_extractor(
            "meta_content",
            lambda x: "".join(
                html.fromstring(x.text).xpath(
                    '/html/body/div[4]/div/main/turbo-frame/div/div/div/div[3]/div[2]/div/div[1]/div/p/text()'
                )
            ),
        )
        self.item_extractor.add_extractor(
            "star",
            lambda x: html.fromstring(x.text).xpath(
                '//span[@id="repo-stars-counter-star"]/text()'
            )[0],
        )
        self.item_extractor.add_extractor(
            "fork",
            lambda x: html.fromstring(x.text).xpath(
                '//span[@id="repo-network-counter"]/text()'
            )[0],
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
        soup = BeautifulSoup(response.text, "html.parser")
        urls = set()
        for node in soup.main.find_all(
            "a", **{"data-ga-click": "Explore, go to repository, location:explore feed"}
        ):
            urls.add(response.url.join(node["href"]))
        for url in urls:
            self.pool.spawn(self.crawl_repo(url))
        self.logger.info("Waiting...")
