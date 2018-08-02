from pytest import raises

from desmod.pool import Pool


def test_pool(env):
    pool = Pool(env, capacity=2)

    def producer(amount, wait):
        yield env.timeout(wait)
        yield pool.put(amount)

    def consumer(expected_amount, wait):
        yield env.timeout(wait)
        msg = yield pool.get(expected_amount)
        assert msg == expected_amount

    env.process(producer(1, 0))
    env.process(producer(2, 1))
    env.process(consumer(1, 0))
    env.process(consumer(2, 1))
    env.process(consumer(2, 2))
    env.process(producer(1, 2))
    env.process(producer(1, 3))
    env.run()


def test_pool_when_full_any(env):
    pool = Pool(env, capacity=9)
    result = []

    def producer(env):
        yield env.timeout(1)
        for i in range(1, 6):
            yield pool.put(i)
            yield env.timeout(1)

    def consumer(env):
        yield env.timeout(5)
        for i in range(1, 3):
            msg = yield pool.get(i)
            assert msg == i

    def full_waiter(env):
        yield pool.when_full()
        assert env.now == 4
        assert pool.level == 10
        result.append('full')

    def any_waiter(env):
        yield pool.when_any()
        assert env.now == 1
        result.append('any')

    def new_waiter(env):
        yield pool.when_new()
        assert env.now == 1
        result.append('new')

    env.process(producer(env))
    env.process(consumer(env))
    env.process(full_waiter(env))
    env.process(any_waiter(env))
    env.process(any_waiter(env))
    env.process(new_waiter(env))
    env.run()
    assert pool.level
    assert pool.is_full
    assert pool.remaining == pool.capacity - pool.level
    assert not pool.is_empty
    assert 'full' in result
    assert 'new' in result
    assert result.count('any') == 2


def test_pool_overflow(env):
    pool = Pool(env, capacity=5, hard_cap=True)

    def producer(env):
        yield env.timeout(1)
        for i in range(5):
            yield pool.put(i)
            yield env.timeout(1)

    env.process(producer(env))
    with raises(OverflowError):
        env.run()


def test_pool_get_more(env):
    pool = Pool(env, capacity=6, name='foo')

    def producer(env):
        yield pool.put(1)
        yield env.timeout(1)
        yield pool.put(1)

    def consumer(env, amount1, amount2):
        amount = yield pool.get(amount1)
        assert amount == amount1
        amount = yield pool.get(amount2)  # should fail
        yield amount

    env.process(producer(env))
    env.process(consumer(env, 1, 10))
    with raises(AssertionError,
                message="Amount {} greater than pool's {} capacity {}".format(
                    10, 'foo', 6)):
        env.run()


def test_pool_cancel(env):
    pool = Pool(env)

    event_cancel = pool.get(2)
    event_cancel.cancel()
    event_full = pool.when_full()
    event_full.cancel()
    event_any = pool.when_any()
    event_any.cancel()
    event_new = pool.when_new()
    event_new.cancel()

    env.run()
    assert pool.level == 0
    assert not event_cancel.triggered
    assert not event_full.triggered
    assert not event_any.triggered
    assert not event_new.triggered


def test_pool_check_str(env):
    pool = Pool(env, name='bar', capacity=5)

    def producer(env, amount):
        yield env.timeout(1)
        yield pool.put(amount)

    env.process(producer(env, 1))
    env.run()
    assert str(pool) == "Pool: name=bar level=1 capacity=5)"
