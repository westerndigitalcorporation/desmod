from desmod.queue import Queue, PriorityQueue


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
        for i in reversed(range(5)):
            yield queue.put(i)
            yield env.timeout(1)

    def consumer(env):
        yield env.timeout(5)
        for i in range(5):
            msg = yield queue.get()
            yield env.timeout(1)
            assert msg == i

    env.process(producer(env))
    env.process(consumer(env))
    env.run()
