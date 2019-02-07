from pytest import raises

from desmod.queue import PriorityItem, PriorityQueue, Queue


def test_mq(env):
    queue = Queue(env, capacity=2)

    def producer(msg, wait):
        yield env.timeout(wait)
        yield queue.put(msg)

    def consumer(expected_msg, wait):
        yield env.timeout(wait)
        msg = yield queue.get()
        assert msg == expected_msg

    env.process(producer('1st', 0))
    env.process(producer('2nd', 1))
    env.process(consumer('1st', 0))
    env.process(consumer('2nd', 1))
    env.run()


def test_queue_peek(env):
    queue = Queue(env)
    assert queue.is_empty
    with raises(IndexError):
        queue.peek()

    queue2 = Queue(env, items=[9, 8, 7])
    assert not queue2.is_empty
    assert queue2.peek() == 9


def test_queue_overflow(env):
    def proc(env, queue):
        yield queue.put(1)
        yield env.timeout(1)
        yield queue.put(1)
        yield env.timeout(1)
        with raises(OverflowError):
            yield queue.put(1)

    queue = Queue(env, capacity=2, hard_cap=True)
    env.process(proc(env, queue))
    env.run()


def test_mq_when_full(env):
    queue = Queue(env, capacity=2)
    result = []

    def producer(env):
        yield env.timeout(1)
        for i in range(5):
            yield queue.put(i)
            yield env.timeout(1)

    def consumer(env):
        yield env.timeout(5)
        for i in range(3):
            msg = yield queue.get()
            assert msg == i

    def full_waiter(env):
        yield queue.when_full()
        result.append('full')

    def any_waiter(env):
        yield queue.when_any()
        assert env.now == 1
        result.append('any')

    env.process(producer(env))
    env.process(consumer(env))
    env.process(full_waiter(env))
    env.process(any_waiter(env))
    env.process(any_waiter(env))
    env.run()
    assert queue.items
    assert queue.is_full
    assert 'full' in result
    assert result.count('any') == 2


def test_priority_mq(env):
    queue = PriorityQueue(env)

    def producer(env):
        for priority in reversed(range(5)):
            item = set([priority])  # unhashable
            yield queue.put(PriorityItem(priority, item))
            yield env.timeout(1)

    def consumer(env):
        yield env.timeout(5)
        for i in range(5):
            msg = yield queue.get()
            assert msg.item == set([i])
            yield env.timeout(1)

    env.process(producer(env))
    env.process(consumer(env))
    env.run()


def test_queue_repr(env):
    queue = Queue(env, name='hi', items=[3, 2, 1])
    assert str(queue) == "Queue(name='hi' size=3 capacity=inf)"

    pri_queue = PriorityQueue(env, capacity=3)
    assert str(pri_queue) == 'PriorityQueue(name=None size=0 capacity=3)'


def test_when_not_full(env):
    queue = Queue(env, capacity=2, items=[0, 1])

    def consumer(env):
        for i in range(2):
            yield env.timeout(3)
            msg = yield queue.get()
            assert msg == i

    def not_full_waiter(env):
        yield queue.when_not_full()
        assert env.now == 3
        yield queue.when_not_full()
        assert env.now == 3

    env.process(consumer(env))
    env.process(not_full_waiter(env))
    env.run()


def test_when_empty(env):
    def proc(env, queue):
        yield queue.when_empty()
        assert env.now == 0

        yield queue.put('a')
        yield queue.put('b')

        with queue.when_empty() as when_empty_ev:
            assert not when_empty_ev.triggered
            yield env.timeout(1)
            item = yield queue.get()
            assert item == 'a'
            assert not when_empty_ev.triggered

        with queue.when_empty() as when_empty_ev:
            assert not when_empty_ev.triggered
            yield env.timeout(1)
            with queue.get() as get_ev:
                item = yield get_ev
                assert item == 'b'
            assert when_empty_ev.triggered
            yield when_empty_ev

    env.process(proc(env, Queue(env)))
    env.run()


def test_when_at_most(env):
    def proc(env, queue):
        for item in 'abc':
            with queue.put(item) as put_ev:
                yield put_ev

        at_most = {}
        at_most[0] = queue.when_at_most(0)
        at_most[3] = queue.when_at_most(3)
        at_most[1] = queue.when_at_most(1)
        at_most[2] = queue.when_at_most(2)
        assert not at_most[0].triggered
        assert not at_most[1].triggered
        assert not at_most[2].triggered
        assert at_most[3].triggered

        item = yield queue.get()
        assert item == 'a'
        assert not at_most[0].triggered
        assert not at_most[1].triggered
        assert at_most[2].triggered

        item = yield queue.get()
        assert item == 'b'
        assert not at_most[0].triggered
        assert at_most[1].triggered

        item = yield queue.get()
        assert item == 'c'
        assert at_most[0].triggered

    env.process(proc(env, Queue(env)))
    env.run()


def test_when_at_least(env):
    def proc(env, queue):
        at_least = {}
        at_least[3] = queue.when_at_least(3)
        at_least[0] = queue.when_at_least(0)
        at_least[2] = queue.when_at_least(2)
        at_least[1] = queue.when_at_least(1)
        assert at_least[0].triggered
        assert not at_least[1].triggered
        assert not at_least[2].triggered
        assert not at_least[3].triggered

        yield queue.put('a')
        assert at_least[1].triggered
        assert not at_least[2].triggered
        assert not at_least[3].triggered

        yield queue.get()
        assert not at_least[2].triggered
        assert not at_least[3].triggered

        yield queue.put('b')
        assert not at_least[2].triggered
        assert not at_least[3].triggered

        yield queue.put('c')
        assert at_least[2].triggered
        assert not at_least[3].triggered

        yield queue.put('d')
        assert at_least[3].triggered

    env.process(proc(env, Queue(env)))
    env.run()


def test_queue_cancel(env):
    queue = Queue(env, capacity=2)

    def producer(env):
        for i in range(5):
            yield env.timeout(5)
            yield queue.put(i)

    def consumer(env):
        for i in range(3):
            yield env.timeout(10)
            msg = yield queue.get()
            assert msg == i

    def canceller(env):
        any_ev = queue.when_any()
        get_ev = queue.get()
        full_ev = queue.when_full()

        yield env.timeout(1)

        assert not get_ev.triggered
        assert not any_ev.triggered
        assert not full_ev.triggered
        get_ev.cancel()
        any_ev.cancel()
        full_ev.cancel()

        assert not queue.is_full
        with queue.when_full() as when_full:
            yield when_full

        with queue.put(1) as put_ev:
            not_full_ev = queue.when_not_full()

            yield env.timeout(1)

            assert not put_ev.triggered
            assert not not_full_ev.triggered
        not_full_ev.cancel()

        yield env.timeout(100)

        assert not get_ev.triggered
        assert not any_ev.triggered
        assert not put_ev.triggered
        assert not put_ev.triggered
        assert not not_full_ev.triggered

    env.process(producer(env))
    env.process(consumer(env))
    env.process(canceller(env))
    env.run()
