# import asyncio
#
# import pytest
#
# from ant_nest import Pool
# from ant_nest import timeout_wrapper
#
#
# def test_pool():
#     pool = Pool()
#     pool.__repr__()
#
#     assert pool.loop is asyncio.get_event_loop()
#     assert pool.limit == -1
#     assert pool.running_count == 0
#     assert not pool.is_running
#     assert pool.status == 'ready'
#
#     pool.reset(limit=1)
#     assert pool.limit == 1
#
#     pool._running_count = 1
#     del pool
#     pool = Pool()
#     del pool
#
