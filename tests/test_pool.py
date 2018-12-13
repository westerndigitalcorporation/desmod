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


def test_pool2(env):
    pool = Pool(env, capacity=2)

    def proc(env, pool):
        assert pool.is_empty
        assert env.now == 0

        yield env.timeout(1)

        when_full = pool.when_full()
        assert not when_full.triggered

        when_any = pool.when_any()
        assert not when_any.triggered

        when_new = pool.when_new()
        assert not when_new.triggered

        with pool.when_not_full() as when_not_full:
            yield when_not_full
            assert when_not_full.triggered

        with raises(ValueError):
            pool.put(pool.capacity + 1)

        with raises(ValueError):
            pool.get(pool.capacity + 1)

        get_two = pool.get(2)
        assert not get_two.triggered

        put_one = pool.put(1)
        assert put_one.triggered

        assert not when_any.triggered
        assert not when_new.triggered
        assert not get_two.triggered
        assert not when_full.triggered
        assert pool.level == 1

        yield put_one
        assert when_any.triggered
        assert when_new.triggered

        yield env.timeout(1)

        when_full2 = pool.when_full()
        assert not when_full2.triggered

        put_one = pool.put(1)
        assert put_one.triggered
        assert not when_full.triggered
        assert not when_full2.triggered

        yield put_one

        assert when_full.triggered
        assert when_full2.triggered
        assert get_two.triggered
        assert pool.level == 0

        yield pool.put(2)

        when_not_full = pool.when_not_full()
        assert not when_not_full.triggered

        yield pool.get(1)

        assert when_not_full.triggered

    env.process(proc(env, pool))
    env.run()


def test_pool_overflow(env):
    pool = Pool(env, capacity=5, hard_cap=True)

    def producer(env):
        yield env.timeout(1)
        yield pool.put(1)
        yield pool.put(3)
        assert pool.remaining == 1
        with raises(OverflowError):
            yield pool.put(2)

    env.process(producer(env))
    env.run()


def test_pool_put_zero(env):
    pool = Pool(env, capacity=5, hard_cap=True)

    def producer(env):
        with raises(ValueError):
            yield pool.put(0)

    env.process(producer(env))
    env.run()


def test_pool_get_zero(env):
    pool = Pool(env, capacity=5, hard_cap=True)

    def consumer(env):
        with raises(ValueError):
            yield pool.get(0)

    env.process(consumer(env))
    env.run()


def test_pool_get_too_many(env):
    def producer(env, pool):
        yield pool.put(1)
        yield env.timeout(1)
        yield pool.put(1)

    def consumer(env, pool):
        amount = yield pool.get(1)
        assert amount == 1
        with raises(ValueError):
            yield pool.get(pool.capacity + 1)

    pool = Pool(env, capacity=6, name='foo')
    env.process(producer(env, pool))
    env.process(consumer(env, pool))
    env.run()


def test_pool_put_too_many(env):
    pool = Pool(env, capacity=6)

    def proc(env):
        with raises(ValueError):
            yield pool.put(pool.capacity + 1)

    env.process(proc(env))
    env.run()


def test_pool_cancel(env):
    pool = Pool(env, capacity=2)

    def proc(env):
        get_ev = pool.get(2)
        full_ev = pool.when_full()
        any_ev = pool.when_any()
        new_ev = pool.when_new()

        yield env.timeout(1)

        any_ev.cancel()
        new_ev.cancel()

        yield pool.put(1)

        assert not get_ev.triggered
        assert not any_ev.triggered
        assert not new_ev.triggered

        get_ev.cancel()
        full_ev.cancel()

        yield pool.put(1)

        assert not get_ev.triggered
        assert pool.is_full
        assert not full_ev.triggered

        put_ev = pool.put(1)
        assert not put_ev.triggered

        yield env.timeout(1)
        put_ev.cancel()

        yield pool.get(1)
        assert not put_ev.triggered

    env.process(proc(env))
    env.run()


def test_pool_check_str(env):
    pool = Pool(env, name='bar', capacity=5)
    assert str(pool) == "Pool(name='bar' level=0 capacity=5)"
