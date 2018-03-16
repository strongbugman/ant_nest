import os
import asyncio

from yarl import URL
import pytest

from ant_nest import *
from ant_nest import CliAnt
from ant_nest.cli import *


def test_request():
    req = Request('GET', URL('http://test.com'))
    assert req.method == 'GET'
    req.__repr__()


def test_response():
    req = Request('GET', URL('http://test.com'))
    res = Response('GET', req.url)
    res._content = b'1'
    assert res.get_text(encoding='utf-8') == '1'
    assert res.simple_text == '1'
    assert res.simple_json == 1

    res = Response('GET', req.url)
    res._content = None
    with pytest.raises(ValueError):
        res.get_text()
    res._content = b'1'
    res.get_encoding = lambda: 'utf-8'
    assert res.get_text() == '1'


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
    assert dict(item.items()) == {'x': 10}
    assert item.x == 10
    with pytest.raises(FieldValidationError):
        item.validate()
    item.z = 1
    item.validate()
    # init with kwargs
    item = TestItem(z=10, a=1)
    assert item.z == 10
    assert item.a == 1
    # repr and str
    item.__repr__()
    item.__str__()
    # subclass

    class SubItem(TestItem):
        a = FloatField()

    item = SubItem()
    assert dict(item.items()) == {'x': 10}
    assert item.x == 10
    item.a = '1.1'
    with pytest.raises(FieldValidationError):  # raise because of "item.z" is not set
        item.validate()
    item.z = '1'
    item.validate()
    assert item.a == 1.1
    assert item.z == 1


def test_extract():
    class TestItem(Item):
        paragraph = StringField()
        title = StringField()

    request = Request('GET', URL('https://www.python.org/'))
    with open('./tests/test.html', 'rb') as f:
        response = Response('GET', request.url)
        response._content = f.read()
        response.get_text(encoding='utf-8')
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

    response = Response('GET', request.url)
    response._content = b'{"a": {"b": {"c": 1}}, "d": null}'
    response.get_text(encoding='utf-8')
    item_extractor = ItemExtractor(TestItem)
    item_extractor.add_jpath('author', 'a.b.c')
    item_extractor.add_jpath('freedom', 'd')
    item = item_extractor.extract(response)
    assert item.author == 1
    assert item.freedom is None  # "None" obj can be extracted from json
    # extract single value with ValueError
    with pytest.raises(ValueError):
        ItemExtractor.extract_value('something else', 'test', 'test')
    # ItemNestExtractor tests
    with open('./tests/test.html', 'rb') as f:
        response = Response('GET', request.url)
        response._content = f.read()
        response.get_text(encoding='utf-8')
    item_nest_extractor = ItemNestExtractor('xpath', '//div[@id="nest"]/div', Item)
    item_nest_extractor.add_xpath('xpath', './p/text()')
    item_nest_extractor.add_regex('regex', 'regex(\d+)</')
    temp = 1
    for item in item_nest_extractor.extract_items(response):
        assert item.xpath == str(temp)
        assert item.regex == str(temp)
        temp += 1

    with pytest.raises(NotImplementedError):
        item_nest_extractor.extract(response)
    # extract with wrappers
    with open('./tests/test.html', 'rb') as f:
        response = Response('GET', request.url)
        response._content = f.read()
        response.get_text(encoding='utf-8')
    assert extract_value_by_xpath('/html/body/div/p/text()', response.html_element) == 'test'
    assert extract_value_by_xpath('/html/body/div/p/text()', response) == 'test'
    assert extract_value_by_xpath('//a/text()', '<a>test</a>', ignore_exception=False) == 'test'
    assert extract_value_by_jpath('a', {'a': 1}) == 1
    assert extract_value_by_jpath('a', '{"a": 1}') == 1
    assert extract_value_by_regex('(\d+)', 'I have 2 apples') == '2'
    assert extract_value_by_jpath('a', {'a': None}) is None
    assert extract_value_by_jpath('a', {}) is None  # default
    assert extract_value_by_jpath('a', {}, default=1) == 1
    with pytest.raises(Exception):
        extract_value_by_jpath('a', None, ignore_exception=False)


def test_cli_get_ants():
    ants = get_ants(['ant_nest'])
    assert CliAnt is list(ants.values())[0]


def test_cli_run_ant():
    ant = CliAnt()
    asyncio.get_event_loop().run_until_complete(run_ant(ant))


def test_cli_open_browser():
    req = Request('GET', URL('http://test.com'))
    res = Response('GET', req.url)
    res._content = b''

    def open_browser_function(url):
        return True

    assert open_response_in_browser(res, _open_browser_function=open_browser_function)


def test_exception_filter():
    class FakeRecord:
        pass

    fr = ExceptionFilter([ThingDropped])
    rc = FakeRecord()
    rc.exc_info = (ThingDropped, None, None)

    assert not fr.filter(rc)
    rc.exc_info = (OSError, None, None)
    assert fr.filter(rc)
