import re

import httpx
import pytest
import jpath
from lxml import html

from ant_nest.things import (
    ItemExtractor,
    set_value_to_item,
    get_value_from_item,
    ItemNestExtractor,
)
from ant_nest.exceptions import ThingDropped, ItemGetValueError, ExceptionFilter


def test_set_get_item():
    class ClsItem:
        pass

    for item in (dict(), ClsItem()):
        set_value_to_item(item, "name", "test")
        assert get_value_from_item(item, "name") == "test"
        with pytest.raises(ItemGetValueError):
            get_value_from_item(item, "name2")


def test_extract_item():
    with open("./tests/test.html", "rb") as f:
        response = httpx.Response(
            200, request=httpx.Request("Get", "https://test.com"), content=f.read()
        )

    class Item:
        pass

    # extract item with xpath and regex
    item_extractor = ItemExtractor(Item)
    item_extractor.add_extractor(
        "paragraph",
        lambda x: html.fromstring(x.text).xpath("/html/body/div/p/text()")[0],
    )
    item_extractor.add_extractor(
        "title", lambda x: re.findall(r"<title>([A-Z a-z]+)</title>", x.text)[0]
    )
    item = item_extractor.extract(response)
    assert item.paragraph == "test"
    assert item.title == "Test html"
    # extract with jpath
    response = httpx.Response(
        200,
        request=httpx.Request("Get", "https://test.com"),
        content=b'{"a": {"b": {"c": 1}}, "d": null}',
    )
    item_extractor = ItemExtractor(Item)
    item_extractor.add_extractor(
        "author", lambda x: jpath.get_all("a.b.c", x.json())[0]
    )
    item_extractor.add_extractor("freedom", lambda x: jpath.get_all("d", x.json())[0])
    item = item_extractor.extract(response)
    assert item.author == 1
    assert item.freedom is None
    # ItemNestExtractor tests
    with open("./tests/test.html", "rb") as f:
        response = httpx.Response(
            200, request=httpx.Request("Get", "https://test.com"), content=f.read()
        )
    item_nest_extractor = ItemNestExtractor(
        Item, lambda x: html.fromstring(x.text).xpath('//div[@id="nest"]/div')
    )
    item_nest_extractor.add_extractor("xpath_key", lambda x: x.xpath("./p/text()")[0])
    item_nest_extractor.add_extractor(
        "regex_key",
        lambda x: re.findall(r"regex(\d+)</", html.tostring(x, encoding="unicode"))[0],
    )
    temp = 1
    for item in item_nest_extractor.extract_items(response):
        assert item.xpath_key == str(temp)
        assert item.regex_key == str(temp)
        temp += 1


def test_exception_filter():
    class FakeRecord:
        pass

    fr = ExceptionFilter()
    rc = FakeRecord()
    rc.exc_info = (ThingDropped, None, None)

    assert not fr.filter(rc)
    rc.exc_info = (OSError, None, None)
    assert fr.filter(rc)
