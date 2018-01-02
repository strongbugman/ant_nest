import os
from multidict import CIMultiDictProxy, CIMultiDict

from aiohttp.backport_cookies import SimpleCookie
import pytest

from ant_nest import *


def test_request():
    req = Request('http://test.com')
    assert req.method == 'GET'


def test_response():
    req = Request('http://test.com')
    res = Response(req, 200, b'1', CIMultiDictProxy(CIMultiDict()), SimpleCookie())
    assert res.text == '1'
    assert res.json == 1


def test_field():
    name = 'test'
    name = IntField.make_shadow_name(name)
    assert IntField.is_shadow_name(name)
    assert IntField.get_name_from_shadow(name) == 'test'


def test_item():

    class TestItem(Item):
        t1 = IntField()
        t2 = FloatField()

    item = TestItem()

    assert len(item) == 0

    item.t1 = '1'
    item.t2 = '0.333'
    assert item.t1 == '1'
    item.validate()
    assert item.t1 == 1
    assert item.t2 == 0.333

    item['t1'] = '2'
    item.validate()
    assert item['t1'] == item.t1
    assert item.get('t1') == 2
    assert item.get('t2') == 0.333
    assert set(item.keys()) == {'t1', 't2'}
    assert set(item.values()) == {2, 0.333}
    assert dict(item.items()) == {'t1': 2, 't2': 0.333}

    with pytest.raises(FieldValidationError):
        item.t1 = '1s'
        item.validate()

    item.t3 = 3
    assert item['t3'] == 3
    del item['t3']

    assert item.pop('t1') == '1s'
    del item['t2']
    with pytest.raises(AttributeError):
        item.t1
    with pytest.raises(KeyError):
        item['t2']
    assert item.get('t1') is None

    item.t1 = 3
    del item.t1
    with pytest.raises(AttributeError):
        item.t1

    # "default" and "null" kwargs
    class TestItem(Item):
        x = IntField(default=10)
        y = StringField(null=True)
        z = IntField()

    item = TestItem()
    assert item.x == 10
    with pytest.raises(FieldValidationError):
        item.validate()
    item.z = 1
    item.validate()

    # init with kwargs
    item = TestItem(z=10, a=1)
    assert item.z == 10
    assert item.a == 1


def test_extract():
    class TestItem(Item):
        paragraph = StringField()
        title = StringField()

    request = Request(url='https://www.python.org/')
    with open('./tests/test.html', 'rb') as f:
        response = Response(request, 200, f.read(), CIMultiDictProxy(CIMultiDict()), SimpleCookie())

    item_extractor = ItemExtractor(TestItem)
    item_extractor.add_xpath('paragraph', '/html/body/div/p/text()')
    item_extractor.add_regex('title', '<title>([A-Z a-z]+)</title>', item_extractor.join_all)
    item = item_extractor.extract(response)
    assert item.paragraph == 'test'
    assert item.title == 'Test html'

    item_extractor.add_xpath('paragraph', '/html/head/title/text()')
    with pytest.raises(ItemExtractError):
        item = item_extractor.extract(response)

    class TestItem(Item):
        author = StringField()

    response = Response(request, 200, b'{"a": {"b": {"c": 1}}}', CIMultiDictProxy(CIMultiDict()), SimpleCookie())
    item_extractor = ItemExtractor(TestItem)
    item_extractor.add_jpath('author', 'a.b.c')
    item = item_extractor.extract(response)
    assert item.author == 1


class MAnt(Ant):
    async def run(self):
        pass


def test_cli_get_ants():
    ants = get_ants(['tests'])
    assert MAnt is list(ants.values())[0]


def test_cli_open_browser():
    req = Request('http://test.com')
    res = Response(req, 200, b'<p>Hello world<\p>', CIMultiDictProxy(CIMultiDict()), SimpleCookie())

    def open_browser_function(url):
        return True

    assert open_response_in_browser(res, _open_browser_function=open_browser_function)
