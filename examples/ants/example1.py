from ant_nest.ant import Ant
from ant_nest.pipelines import ItemFieldReplacePipeline
from bs4 import BeautifulSoup
from lxml import html
from yarl import URL


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
        element = html.fromstring(response.simple_text)
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
        soup = BeautifulSoup(response.simple_text, "html.parser")
        for node in soup.main.find_all(
            "a", **{"data-ga-click": "Repository, go to repository"}
        ):
            self.schedule_task(self.crawl_repo(response.url.join(URL(node["href"]))))
        self.logger.info("Waiting...")
