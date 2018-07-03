import sys
import asyncio
from unittest import mock

from yarl import URL
import pytest

from ant_nest import *
from ant_nest import CliAnt
from ant_nest.cli import *
from ant_nest import cli


def fake_response(content):
    res = Response('GET', URL('http://test.com'), writer=None,
                   continue100=None, timer=None,
                   request_info=None, traces=None,
                   loop=asyncio.get_event_loop(),
                   session=None)
    res._content = content
    res._body = content

    return res


def test_request():
    req = Request('GET', URL('http://test.com'))
    assert req.method == 'GET'
    req.__repr__()


def test_response():
    res = fake_response(b'1')
    assert res.get_text(encoding='utf-8') == '1'
    assert res.simple_text == '1'
    assert res.simple_json == 1

    res = fake_response(None)
    with pytest.raises(ValueError):
        res.get_text()
    res = fake_response(b'1')
    res.get_encoding = lambda: 'utf-8'
    res._get_encoding = lambda: 'utf-8'
    assert res.get_text() == '1'

    res = fake_response(b'')

    def open_browser_function(url):
        return True

    assert res.open_in_browser(_open_browser_function=open_browser_function)


def test_item_set_read():
    class ClsItem:
        pass

    for item in (dict(), ClsItem()):
        set_value_to_item(item, 'name', 'test')
        assert get_value_from_item(item, 'name') == 'test'
        assert get_value_from_item(item, 'name2', default='test') == 'test'
        with pytest.raises(ItemGetValueError):
            get_value_from_item(item, 'name2')


def test_extract():
    with open('./tests/test.html', 'rb') as f:
        response = fake_response(f.read())
        response.get_text(encoding='utf-8')

    class Item:
        pass
    # extract item with xpath and regex
    item_extractor = ItemExtractor(Item)
    item_extractor.add_pattern('xpath', 'paragraph', '/html/body/div/p/text()')
    item_extractor.add_pattern('regex', 'title', '<title>([A-Z a-z]+)</title>',
                               item_extractor.EXTRACT_WITH_JOIN_ALL)
    item = item_extractor.extract(response)
    assert item.paragraph == 'test'
    assert item.title == 'Test html'
    # raise exception it can`t find one key
    item_extractor.add_pattern('regex', 'test', 'test(\d+)test')
    with pytest.raises(ItemExtractError):
        item_extractor.extract(response)
    # with exception for multiple result
    item_extractor.add_pattern('xpath', 'paragraph', '/html/head/title/text()')
    with pytest.raises(ItemExtractError):
        item_extractor.extract(response)
    # extract with jpath
    response = fake_response(b'{"a": {"b": {"c": 1}}, "d": null}')
    response.get_text(encoding='utf-8')
    item_extractor = ItemExtractor(Item)
    item_extractor.add_pattern('jpath', 'author', 'a.b.c')
    item_extractor.add_pattern('jpath', 'freedom', 'd')
    item = item_extractor.extract(response)
    assert item.author == 1
    assert item.freedom is None  # "None" obj can be extracted from json
    with pytest.raises(ValueError):
        item_extractor.add_pattern('other', 'key', 'pattern')
    # extract single value with ValueError
    with pytest.raises(ValueError):
        ItemExtractor.extract_value('something else', 'test', 'test')
    # ItemNestExtractor tests
    with open('./tests/test.html', 'rb') as f:
        response = fake_response(f.read())
        response.get_text(encoding='utf-8')
    item_nest_extractor = ItemNestExtractor(
        'xpath', '//div[@id="nest"]/div', Item)
    item_nest_extractor.add_pattern('xpath', 'xpath', './p/text()')
    item_nest_extractor.add_pattern('regex', 'regex', 'regex(\d+)</')
    temp = 1
    for item in item_nest_extractor.extract_items(response):
        assert item.xpath == str(temp)
        assert item.regex == str(temp)
        temp += 1

    with pytest.raises(NotImplementedError):
        item_nest_extractor.extract(response)
    # extract with wrappers
    with open('./tests/test.html', 'rb') as f:
        response = fake_response(f.read())
        response.get_text(encoding='utf-8')
    assert ItemExtractor.extract_value(
        'xpath', '/html/body/div/p/text()', response.html_element) == 'test'
    assert ItemExtractor.extract_value(
        'xpath', '/html/body/div/p/text()', response) == 'test'
    assert ItemExtractor.extract_value(
        'xpath', '//a/text()', '<a>test</a>') == 'test'
    assert ItemExtractor.extract_value('jpath', 'a', {'a': 1}) == 1
    assert ItemExtractor.extract_value('jpath', 'a', '{"a": 1}') == 1
    assert ItemExtractor.extract_value(
        'regex', '(\d+)', 'I have 2 apples') == '2'
    assert ItemExtractor.extract_value('jpath', 'a', {'a': None}) is None
    assert ItemExtractor.extract_value('jpath', 'a', {}, default=1) == 1
    with pytest.raises(ItemExtractError):
        ItemExtractor.extract_value('jpath', 'a', {})


def test_cli_get_ants():
    ants = get_ants(['ant_nest', 'tests'])
    assert CliAnt is list(ants.values())[0]


def test_cli_shutdown():
    ant = CliAnt()
    ant._queue.put_nowait(object())
    cli.shutdown_ant(ant)
    assert ant._is_closed
    assert ant._queue.qsize() == 0

    with pytest.raises(SystemExit):
        cli.shutdown_ant(ant)


def test_cli():

    with pytest.raises(SystemExit):
        cli.main(['-v'])

    with pytest.raises(SystemExit):  # no settings.py
        cli.main(['-l'])

    from ant_nest import _settings_example as settings
    # mock settings.py import
    sys.modules['settings'] = settings

    settings.ANT_PACKAGES = ['NoAnts']
    with pytest.raises(SystemExit):  # can`t import NoAnts
        cli.main(['-l'])

    settings.ANT_PACKAGES = ['ant_nest.things']
    with pytest.raises(SystemExit):  # no ants can be found
        cli.main(['-l'])

    settings.ANT_PACKAGES = ['tests']
    cli.main(['-l'])

    with pytest.raises(SystemExit):  # FakeAnt not exist
        cli.main(['-a' 'FakeAnt'])
        cli.main(['-l'])

    with pytest.raises(SystemExit), mock.patch('os.mkdir', lambda x: None), \
            mock.patch('shutil.copyfile', lambda *args: None):
        cli.main(['-c' '.'])

    cli.main(['-a' 'tests.test_things.CliAnt'])


def test_exception_filter():
    class FakeRecord:
        pass

    fr = ExceptionFilter()
    rc = FakeRecord()
    rc.exc_info = (ThingDropped, None, None)

    assert not fr.filter(rc)
    rc.exc_info = (OSError, None, None)
    assert fr.filter(rc)
