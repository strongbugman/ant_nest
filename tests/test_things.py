import os
from multidict import CIMultiDictProxy, CIMultiDict

from aiohttp.backport_cookies import SimpleCookie
import pytest

from ant_nest import *


def test_request():
    req = Request('http://test.com')
    assert req.method == 'GET'
    req.__repr__()


def test_response():
    req = Request('http://test.com')
    res = Response(req, 200, b'1', CIMultiDictProxy(CIMultiDict()), SimpleCookie())
    assert res.text == '1'
    assert res.json == 1
    res.__repr__()


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

    # set by attribute
    item.t1 = '1'
    item.t2 = '0.333'
    assert item.t1 == '1'
    item.validate()
    assert item.t1 == 1
    assert item.t2 == 0.333
    # set by key name
    item['t1'] = '2'
    item.validate()
    assert item['t1'] == item.t1
    assert item.get('t1') == 2
    assert item.get('t2') == 0.333
    assert set(item.keys()) == {'t1', 't2'}
    assert set(item.values()) == {2, 0.333}
    assert dict(item.items()) == {'t1': 2, 't2': 0.333}
    # validate
    with pytest.raises(FieldValidationError):
        item.t1 = '1s'
        item.validate()
    # delete
    item.t3 = 3
    assert item['t3'] == 3
    del item['t3']
    # pop
    assert item.pop('t1') == '1s'
    del item['t2']
    with pytest.raises(AttributeError):
        item.t1
    with pytest.raises(KeyError):
        item.__delitem__('t2')
    assert item.get('t1') is None
    # set with exception
    with pytest.raises(KeyError):
        item[1] = 2
    with pytest.raises(AttributeError):
        item.__setattr__(2, 2)
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

    item.__repr__()
    item.__str__()


def test_extract():
    class TestItem(Item):
        paragraph = StringField()
        title = StringField()

    request = Request(url='https://www.python.org/')
    with open('./tests/test.html', 'rb') as f:
        response = Response(request, 200, f.read(), CIMultiDictProxy(CIMultiDict()), SimpleCookie())
    # extract item with xpath and regex
    item_extractor = ItemExtractor(TestItem)
    item_extractor.add_xpath('paragraph', '/html/body/div/p/text()')
    item_extractor.add_regex('title', '<title>([A-Z a-z]+)</title>', item_extractor.extract_with_join_all)
    item = item_extractor.extract(response)
    assert item.paragraph == 'test'
    assert item.title == 'Test html'
    # some exception will be ignored
    item_extractor.add_regex('test', 'test(\d+)test')
    item = item_extractor.extract(response)
    assert 'test' not in item  # "test" key`s value can`t be find
    # with exception for multiple result
    item_extractor.add_xpath('paragraph', '/html/head/title/text()')
    with pytest.raises(ItemExtractError):
        item = item_extractor.extract(response)
    # extract with jpath

    class TestItem(Item):
        author = StringField()

    response = Response(request, 200, b'{"a": {"b": {"c": 1}}, "d": null}', CIMultiDictProxy(CIMultiDict()), SimpleCookie())
    item_extractor = ItemExtractor(TestItem)
    item_extractor.add_jpath('author', 'a.b.c')
    item_extractor.add_jpath('freedom', 'd')
    item = item_extractor.extract(response)
    assert item.author == 1
    assert item.freedom is None  # "None" obj can be extracted from json
    # extract single value with ValueError
    with pytest.raises(ValueError):
        ItemExtractor.extract_value('something else', 'test', 'test')
    # extract with wrappers
    with open('./tests/test.html', 'rb') as f:
        response = Response(request, 200, f.read(), CIMultiDictProxy(CIMultiDict()), SimpleCookie())
    assert extract_value_by_xpath('/html/body/div/p/text()', response.html_element) == 'test'
    assert extract_value_by_jpath('a', {'a': 1}) == 1
    assert extract_value_by_regex('(\d+)', 'I have 2 apples') == '2'
    assert extract_value_by_jpath('a', {}) is None
    assert extract_value_by_jpath('a', {}, default=1) == 1
    with pytest.raises(Exception):
        extract_value_by_jpath('a', None, ignore_exception=False)


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
