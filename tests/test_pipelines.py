import os
import io

import pytest
from yarl import URL
import aiofiles

from ant_nest import pipelines as pls
from ant_nest.things import Request
from ant_nest.exceptions import ThingDropped
from .test_things import fake_response


@pytest.mark.asyncio
async def test_pipeline():
    pl = pls.Pipeline()
    pl.process(Request("GET", URL("https://test.com")))


def test_response_filter_error_pipeline():
    pl = pls.ResponseFilterErrorPipeline()
    res = fake_response(b"")
    err_res = fake_response(b"")
    res.status = 200
    err_res.status = 403
    assert res is pl.process(res)
    with pytest.raises(ThingDropped):
        pl.process(err_res)


def test_request_duplicate_filter_pipeline():
    pl = pls.RequestDuplicateFilterPipeline()
    req = Request("GET", URL("http://test.com"))
    assert pl.process(req) is req
    with pytest.raises(ThingDropped):
        pl.process(req)


def test_item_print_pipeline(item_cls):
    pl = pls.ItemPrintPipeline()
    item = item_cls()
    item.count = 3
    item.info = "hi"
    assert pl.process(item) is item


def test_item_filed_replace_pipeline(item_cls):
    pl = pls.ItemFieldReplacePipeline(["info"])
    item = item_cls()
    item.info = "hi\n,\t\r ant\n"
    pl.process(item)
    assert item.info == "hi, ant"


@pytest.mark.asyncio
async def test_item_base_file_dump_pipeline():
    pl = pls.ItemBaseFileDumpPipeline()
    await pl.dump("/dev/null", "Hello World")
    await pl.dump("/dev/null", b"Hello World")
    await pl.dump("/dev/null", io.StringIO("Hello World"))
    await pl.dump("/dev/null", io.BytesIO(b"Hello World"))
    await pl.dump("/dev/null", open("./tests/test.html"), buffer_size=4)
    async with aiofiles.open("./tests/test.html") as f:
        await pl.dump("/dev/null", f)
    async with aiofiles.open("./tests/test.html", "rb") as f:
        await pl.dump("/dev/null", f, buffer_size=4)

    with pytest.raises(ValueError):
        await pl.dump("/dev/null", None)


@pytest.mark.asyncio
async def test_item_json_dump_pipeline(item_cls):
    pl = pls.ItemJsonDumpPipeline(to_dict=lambda x: x)
    item = item_cls()
    item.count = 1
    assert pl.process(item) is item
    item = item_cls()
    item.info = "hi"
    pl.process(item)
    await pl.on_spider_close()

    # clean file
    ci = os.getenv("TEST_HOST", "localhost")
    if ci == "localhost":
        os.remove("./Item.json")


def test_request_user_agent_pipeline():
    pl = pls.RequestUserAgentPipeline(user_agent="ant")
    req = Request("GET", URL("https://www.hi.com"))
    assert pl.process(req) is req
    assert req.headers["User-Agent"] == "ant"

    req.headers["User-Agent"] = "custom"
    assert pl.process(req).headers["User-Agent"] == "custom"


def test_request_random_user_agent_pipeline():
    pl = pls.RequestRandomUserAgentPipeline()
    req = Request("GET", URL("https://www.hi.com"))
    assert pl.process(req) is req
    assert req.headers.get("User-Agent") is not None

    req.headers["User-Agent"] = "custom"
    assert pl.process(req).headers["User-Agent"] == "custom"

    with pytest.raises(ValueError):
        pls.RequestRandomUserAgentPipeline(system="something")

    with pytest.raises(ValueError):
        pls.RequestRandomUserAgentPipeline(browser="something")

    pl = pls.RequestRandomUserAgentPipeline(system="UnixLike", browser="Firefox")
    user_agent = pl.create()
    assert "X11" in user_agent
    assert "Firefox" in user_agent
