import sys
import asyncio
from unittest import mock
import re

from yarl import URL
import pytest
import jpath
from lxml import html

from ant_nest.ant import CliAnt
from ant_nest.cli import get_ants
from ant_nest.things import (
    Response,
    Request,
    ItemExtractor,
    set_value_to_item,
    get_value_from_item,
    ItemNestExtractor,
)
from ant_nest.exceptions import ThingDropped, ItemGetValueError, ExceptionFilter
from ant_nest import cli


def fake_response(content):
    res = Response(
        "GET",
        URL("http://test.com"),
        writer=None,
        continue100=None,
        timer=None,
        request_info=None,
        traces=None,
        loop=asyncio.get_event_loop(),
        session=None,
    )
    res._content = content
    res._body = content

    return res


def test_request():
    req = Request("GET", URL("http://test.com"))
    assert req.method == "GET"
    req.__repr__()


def test_response():
    res = fake_response(b"1")
    assert res.get_text(encoding="utf-8") == "1"
    assert res.simple_text == "1"
    assert res.simple_json == 1

    res = fake_response(None)
    with pytest.raises(ValueError):
        res.get_text()
    res = fake_response(b"1")
    res.get_encoding = lambda: "utf-8"
    res._get_encoding = lambda: "utf-8"
    assert res.get_text() == "1"

    res = fake_response(b"")

    def open_browser_function(url):
        return True

    assert res.open_in_browser(_open_browser_function=open_browser_function)


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
        response = fake_response(f.read())
        response.get_text(encoding="utf-8")

    class Item:
        pass

    # extract item with xpath and regex
    item_extractor = ItemExtractor(Item)
    item_extractor.add_extractor(
        "paragraph", lambda x: x.html_element.xpath("/html/body/div/p/text()")[0]
    )
    item_extractor.add_extractor(
        "title", lambda x: re.findall(r"<title>([A-Z a-z]+)</title>", x.simple_text)[0]
    )
    item = item_extractor.extract(response)
    assert item.paragraph == "test"
    assert item.title == "Test html"
    # extract with jpath
    response = fake_response(b'{"a": {"b": {"c": 1}}, "d": null}')
    response.get_text(encoding="utf-8")
    item_extractor = ItemExtractor(Item)
    item_extractor.add_extractor(
        "author", lambda x: jpath.get_all("a.b.c", x.simple_json)[0]
    )
    item_extractor.add_extractor(
        "freedom", lambda x: jpath.get_all("d", x.simple_json)[0]
    )
    item = item_extractor.extract(response)
    assert item.author == 1
    assert item.freedom is None
    # ItemNestExtractor tests
    with open("./tests/test.html", "rb") as f:
        response = fake_response(f.read())
        response.get_text(encoding="utf-8")
    item_nest_extractor = ItemNestExtractor(
        Item, lambda x: x.html_element.xpath('//div[@id="nest"]/div')
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


def test_cli_get_ants():
    ants = get_ants(["ant_nest", "tests"])
    assert CliAnt is list(ants.values())[0]


def test_cli_shutdown():
    ant = CliAnt()
    ant._queue.put_nowait(object())
    cli.shutdown_ant([ant])
    assert ant._is_closed
    assert ant._queue.qsize() == 0

    with pytest.raises(SystemExit):
        cli.shutdown_ant([ant])


def test_cli():

    with pytest.raises(SystemExit):
        cli.main(["-v"])

    with pytest.raises(SystemExit):  # no settings.py
        cli.main(["-l"])

    from ant_nest import _settings_example as settings

    # mock settings.py import
    sys.modules["settings"] = settings

    settings.ANT_PACKAGES = ["NoAnts"]
    with pytest.raises(ModuleNotFoundError):  # can`t import NoAnts
        cli.main(["-l"])

    settings.ANT_PACKAGES = ["ant_nest.things"]
    with pytest.raises(SystemExit):  # no ants can be found
        cli.main(["-l"])

    settings.ANT_PACKAGES = ["tests"]
    cli.main(["-l"])

    with pytest.raises(SystemExit):  # FakeAnt not exist
        cli.main(["-a" "FakeAnt"])
        cli.main(["-l"])

    with pytest.raises(SystemExit), mock.patch("os.mkdir", lambda x: None), mock.patch(
        "shutil.copyfile", lambda *args: None
    ):
        cli.main(["-c" "."])

    cli.main(["-a" "tests.test_things.CliAnt"])


def test_exception_filter():
    class FakeRecord:
        pass

    fr = ExceptionFilter()
    rc = FakeRecord()
    rc.exc_info = (ThingDropped, None, None)

    assert not fr.filter(rc)
    rc.exc_info = (OSError, None, None)
    assert fr.filter(rc)
