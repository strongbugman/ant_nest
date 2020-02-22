import pytest
import asyncio

from ant_nest.reporter import Reporter


@pytest.mark.asyncio
async def test_ant_report():
    item = {}
    reporter = Reporter(slot=1)
    # request report
    reporter.report(item)
    assert reporter._records["dict"].count == 1
    assert reporter._records["dict"].last_count == 0
    # dropped item
    reporter.report(item, dropped=True)
    assert reporter._records["dict"].dropped_count == 1
    assert reporter._records["dict"].dropped_last_count == 0
    # waiting log
    await asyncio.sleep(2)
    reporter.close()
