import pytest
import pickle
import os

from ant_nest.things import (
    Request, Response, Item, IntField, FloatField, StringField, FiledValidationError, ItemExtractor, ItemExtractError)
from ant_nest.pipelines import Pipeline
from ant_nest.ant import Ant
from ant_nest import cli
from ant_nest.exceptions import ThingDropped


def test_request():
    req = Request('http://test.com')
    assert req.method == 'GET'
    file_path = './tests/req'
    with open(file_path, 'wb') as f:
        pickle.dump(req, f)
    with open(file_path, 'rb') as f:
        req_l = pickle.load(f)
    assert req.url == req_l.url
    os.remove(file_path)


def test_response():
    req = Request('http://test.com')
    res = Response(req, 200, b'1', {})
    assert res.text == '1'
    assert res.json == 1
    file_path = './tests/res'
    with open(file_path, 'wb') as f:
        pickle.dump(res, f)
    with open(file_path, 'rb') as f:
        res_l = pickle.load(f)
    assert res.url == res_l.url
    assert res.request.url == res_l.request.url
    os.remove(file_path)


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

    with pytest.raises(FiledValidationError):
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


@pytest.mark.asyncio
async def test_pipelines():
    class TestAnt(Ant):
        async def run(self):
            return None

    pls = [Pipeline() for x in range(10)]
    thing = Request('test_url')
    ant = TestAnt()
    assert thing is await ant._handle_thing_with_pipelines(thing, pls)

    class TestPipeline(Pipeline):
        async def process(self, ant, thing):
            return None

    pls[5] = TestPipeline()
    with pytest.raises(ThingDropped):
        await ant._handle_thing_with_pipelines(thing, pls)


@pytest.mark.asyncio
async def test_ant():
    class TestAnt(Ant):
        async def run(self):
            await self.request('test.com')

        async def _request(self, req: Request):
            return Response(req, 200, b'1', {})

    await TestAnt().main()


def test_extract():
    class TestItem(Item):
        paragraph = StringField()

    request = Request(url='https://www.python.org/')
    with open('./tests/test.html', 'rb') as f:
        response = Response(request, 200, f.read())

    item_extractor = ItemExtractor(TestItem)
    item_extractor.add_xpath('paragraph', '/html/body/div/p/text()')
    item = item_extractor.extract(response)
    assert item.paragraph == 'test'

    item_extractor.add_xpath('paragraph', '/html/head/title/text()')
    with pytest.raises(ItemExtractError):
        item = item_extractor.extract(response)


class MAnt(Ant):
    async def run(self):
        pass


def test_cli_get_ants():
    ants = cli.get_ants(['tests'])
    assert MAnt is list(ants.values())[0]


def test_cli_open_browser():
    req = Request('http://test.com')
    res = Response(req, 200, b'<p>Hello world<\p>', {})

    def open_browsere_function(url):
        return True

    assert cli.open_response_in_browser(res, _open_browser_function=open_browsere_function)


@pytest.mark.asyncio
async def test_ant_ensure_future():

    class TAnt(Ant):

        def __init__(self, limit):
            super().__init__()
            self._Ant__limit = limit
            self.count = 0
            self.max_count = 10

        async def cor(self):
            self.count += 1

        async def run(self):
            for i in range(self.max_count):
                self.ensure_future(self.cor())

    ant = TAnt(3)
    await ant.main()
    assert ant.count == ant.max_count

    class ATAnt(TAnt):
        async def run(self):
            for c in self.as_completed((self.cor() for i in range(self.max_count))):
                await c

    ant = ATAnt(3)
    await ant.main()
    assert ant.count == ant.max_count
