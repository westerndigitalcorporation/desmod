from desmod.probe import attach
from desmod.queue import Queue
from desmod.pool import Pool

import pytest
import simpy


@pytest.fixture
def env():
    return simpy.Environment()


def test_attach_bad_type(env):
    values = []
    with pytest.raises(TypeError):
        attach('scope', 'a string', [values.append])


def test_attach_method():
    values = []

    class C(object):
        def __init__(self):
            self.x = 0

        def doit(self):
            self.x += 1
            return self.x

    c = C()
    attach('scope', c.doit, [values.append])
    c.doit()
    c.doit()
    c.doit()
    assert values == [1, 2, 3]


def test_attach_container(env):
    values = []
    container = simpy.Container(env)
    attach('scope', container, [values.append])

    def proc():
        yield container.put(2)
        yield container.get(1)

    env.process(proc())
    env.run()
    assert values == [2, 1]


def test_attach_store(env):
    values = []
    store = simpy.Store(env)
    attach('scope', store, [values.append])

    def proc():
        yield store.put('item0')
        yield store.put('item1')
        yield store.put('item2')
        item = yield store.get()
        assert item == 'item0'

    env.process(proc())
    env.run()
    assert values == [1, 2, 3, 2]


def test_attach_resource_users(env):
    values = []
    resource = simpy.Resource(env, capacity=3)
    attach('scope', resource, [values.append])

    def proc():
        with resource.request() as req:
            yield req
            with resource.request() as req:
                yield req
            with resource.request() as req:
                yield req

    env.process(proc())
    env.run()
    assert values == [1, 2, 1, 2, 1, 0]


def test_attach_resource_queue(env):
    values = []
    resource = simpy.Resource(env)
    attach('scope', resource, [values.append], trace_queue=True)

    def proc(t):
        with resource.request() as req:
            yield req
            yield env.timeout(t)

    env.process(proc(1))
    env.process(proc(2))
    env.process(proc(3))
    env.run()
    assert values == [0, 1, 2, 1, 0]


def test_attach_queue_size(env):
    values = []
    queue = Queue(env)
    attach('scope', queue, [values.append])

    def proc():
        yield queue.put('item0')
        yield queue.put('item1')
        yield queue.put('item2')
        item = yield queue.get()
        assert item == 'item0'

    env.process(proc())
    env.run()
    assert values == [1, 2, 3, 2]


def test_attach_queue_remaining(env):
    values = []
    queue = Queue(env, capacity=10)

    attach('scope', queue, [values.append], trace_remaining=True)

    def proc():
        yield queue.put('item0')
        yield queue.put('item1')
        yield queue.put('item2')
        item = yield queue.get()
        assert item == 'item0'

    env.process(proc())
    env.run()
    assert values == [9, 8, 7, 8]


def test_attach_pool_level(env):
    values = []
    pool = Pool(env)
    attach('scope', pool, [values.append])

    def proc():
        yield pool.put(1)
        yield pool.put(1)
        yield pool.put(1)
        item = yield pool.get(1)
        assert item == 1

    env.process(proc())
    env.run()
    assert values == [1, 2, 3, 2]


def test_attach_pool_remaining(env):
    values = []
    pool = Pool(env, capacity=10)

    attach('scope', pool, [values.append], trace_remaining=True)

    def proc():
        yield pool.put(1)
        yield pool.put(1)
        yield pool.put(1)
        item = yield pool.get(3)
        assert item == 3

    env.process(proc())
    env.run()
    assert values == [9, 8, 7, 10]
