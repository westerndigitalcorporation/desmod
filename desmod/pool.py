"""Pool class for modeling a container of resources.

A pool models a container of items or resources. Pool is similar to the :class:
`simpy.resources.Container`, but with additional events when the Container is
empty or full. Users can put or get items in the pool with a certain amount as
a parameter.
"""

from simpy import Event
from simpy.core import BoundClass


class PoolEvent(Event):
    def __init__(self, pool):
        super(PoolEvent, self).__init__(pool.env)
        self.pool = pool
        pool._waiters.setdefault(type(self), []).append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()

    def cancel(self):
        if not self.triggered:
            self.pool._waiters[type(self)].remove(self)
            self.callbacks = None


class PoolPutEvent(PoolEvent):
    def __init__(self, pool, amount=1):
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        self.amount = amount
        super(PoolPutEvent, self).__init__(pool)
        self.callbacks.extend(
            [
                pool._trigger_when_full,
                pool._trigger_when_new,
                pool._trigger_when_any,
                pool._trigger_get,
            ]
        )
        pool._trigger_put()


class PoolGetEvent(PoolEvent):
    def __init__(self, pool, amount=1):
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        self.amount = amount
        super(PoolGetEvent, self).__init__(pool)
        self.callbacks.extend(
            [
                pool._trigger_when_not_full,
                pool._trigger_put,
            ]
        )
        pool._trigger_get()


class PoolWhenNewEvent(PoolEvent):
    pass


class PoolWhenAnyEvent(PoolEvent):
    def __init__(self, pool):
        super(PoolWhenAnyEvent, self).__init__(pool)
        pool._trigger_when_any()


class PoolWhenFullEvent(PoolEvent):
    def __init__(self, pool):
        super(PoolWhenFullEvent, self).__init__(pool)
        pool._trigger_when_full()


class PoolWhenNotFullEvent(PoolEvent):
    def __init__(self, pool):
        super(PoolWhenNotFullEvent, self).__init__(pool)
        pool._trigger_when_not_full()


class Pool(object):
    """Simulation pool of discrete or continuous resources.

    `Pool` is similar to :class:`simpy.resources.Container`.
    It provides a simulation-aware container for managing a shared pool of
    resources. The resources can be either discrete objects (like apples) or
    continuous (like water).

    Resources are added and removed using :meth:`put()` and :meth:`get()`.

    :param env: Simulation environment.
    :param capacity: Capacity of the pool; infinite by default.
    :param hard_cap:
        If specified, the pool overflows when the `capacity` is reached.
    :param init_level: Initial level of the pool.
    :param name: Optional name to associate with the queue.

    """

    def __init__(self, env, capacity=float('inf'), init=0, hard_cap=False,
                 name=None):
        self.env = env
        #: Capacity of the pool (maximum level).
        self.capacity = capacity
        #: Current fill level of the pool.
        self.level = init
        self._hard_cap = hard_cap
        self.name = name
        self._waiters = {}
        self._put_hook = None
        self._get_hook = None
        BoundClass.bind_early(self)

    @property
    def remaining(self):
        """Remaining pool capacity."""
        return self.capacity - self.level

    @property
    def is_empty(self):
        """Indicates whether the pool is empty."""
        return self.level == 0

    @property
    def is_full(self):
        """Indicates whether the pool is full."""
        return self.level >= self.capacity

    #: Put amount in the pool.
    put = BoundClass(PoolPutEvent)

    #: Get amount from the pool.
    get = BoundClass(PoolGetEvent)

    #: Return an event triggered when the pool is non-empty.
    when_any = BoundClass(PoolWhenAnyEvent)

    #: Return an event triggered when items are put in pool
    when_new = BoundClass(PoolWhenNewEvent)

    #: Return an event triggered when the pool becomes full.
    when_full = BoundClass(PoolWhenFullEvent)

    #: Return an event triggered when the pool becomes not full.
    when_not_full = BoundClass(PoolWhenNotFullEvent)

    def _trigger_put(self, _=None):
        waiters = self._waiters.get(PoolPutEvent)
        idx = 0
        while waiters and idx < len(waiters):
            put_ev = waiters[idx]
            if self.capacity - self.level >= put_ev.amount:
                waiters.pop(idx)
                self.level += put_ev.amount
                put_ev.succeed()
                if self._put_hook:
                    self._put_hook()
            elif self._hard_cap:
                raise OverflowError()
            else:
                idx += 1

    def _trigger_get(self, _=None):
        waiters = self._waiters.get(PoolGetEvent)
        idx = 0
        while waiters and idx < len(waiters):
            get_ev = waiters[idx]
            if get_ev.amount <= self.level:
                waiters.pop(idx)
                self.level -= get_ev.amount
                get_ev.succeed(get_ev.amount)
                if self._get_hook:
                    self._get_hook()
            else:
                idx += 1

    def _trigger_when_new(self, _=None):
        waiters = self._waiters.get(PoolWhenNewEvent)
        if waiters:
            for when_new_ev in waiters:
                when_new_ev.succeed()
            del waiters[:]

    def _trigger_when_any(self, _=None):
        waiters = self._waiters.get(PoolWhenAnyEvent)
        if waiters and self.level:
            for when_any_ev in waiters:
                when_any_ev.succeed()
            del waiters[:]

    def _trigger_when_full(self, _=None):
        waiters = self._waiters.get(PoolWhenFullEvent)
        if waiters and self.level >= self.capacity:
            for when_full_ev in waiters:
                when_full_ev.succeed()
            del waiters[:]

    def _trigger_when_not_full(self, _=None):
        waiters = self._waiters.get(PoolWhenNotFullEvent)
        if waiters and self.level < self.capacity:
            for when_not_full_ev in waiters:
                when_not_full_ev.succeed()
            del waiters[:]

    def __repr__(self):
        return (
            '{0.__class__.__name__}(name={0.name!r} level={0.level}'
            ' capacity={0.capacity})'
        ).format(self)
