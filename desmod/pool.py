"""Pool class for modeling a container of resources.

A pool models a container of items or resources. Pool is similar to the :class:
`simpy.resources.Container`, but with additional events when the Container is
empty or full. Users can put or get items in the pool with a certain amount as
a parameter.
"""

from simpy import Event
from simpy.core import BoundClass


class PoolPutEvent(Event):
    def __init__(self, pool, amount=1):
        super(PoolPutEvent, self).__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.callbacks.append(pool._trigger_get)
        pool._putters.append(self)
        pool._trigger_put()

    def cancel(self):
        if not self.triggered:
            self.pool._putters.remove(self)
            self.callbacks = None


class PoolGetEvent(Event):
    def __init__(self, pool, amount=1):
        super(PoolGetEvent, self).__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.callbacks.append(pool._trigger_put)
        pool._getters.append(self)
        pool._trigger_get()

    def cancel(self):
        if not self.triggered:
            self.pool._getters.remove(self)
            self.callbacks = None


class PoolWhenNewEvent(Event):
    def __init__(self, pool):
        super(PoolWhenNewEvent, self).__init__(pool.env)
        self.pool = pool
        pool._new_waiters.append(self)

    def cancel(self):
        if not self.triggered:
            self.pool._new_waiters.remove(self)
            self.callbacks = None


class PoolWhenAnyEvent(Event):
    def __init__(self, pool):
        super(PoolWhenAnyEvent, self).__init__(pool.env)
        self.pool = pool
        pool._any_waiters.append(self)
        pool._trigger_when_any()

    def cancel(self):
        if not self.triggered:
            self.pool._any_waiters.remove(self)
            self.callbacks = None


class PoolWhenFullEvent(Event):
    def __init__(self, pool):
        super(PoolWhenFullEvent, self).__init__(pool.env)
        self.pool = pool
        pool._full_waiters.append(self)
        pool._trigger_when_full()

    def cancel(self):
        if not self.triggered:
            self.pool._full_waiters.remove(self)
            self.callbacks = None


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

    def __init__(self, env, capacity=float('inf'), hard_cap=False,
                 init_level=0, name=None):
        self.env = env
        #: Capacity of the queue (maximum number of items).
        self.capacity = capacity
        self._hard_cap = hard_cap
        self.level = init_level
        self.name = name
        self._putters = []
        self._getters = []
        self._new_waiters = []
        self._any_waiters = []
        self._full_waiters = []
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

    #: Put amount items in the pool.
    put = BoundClass(PoolPutEvent)

    #: Get amount items from the queue.
    get = BoundClass(PoolGetEvent)

    #: Return an event triggered when the pool is non-empty.
    when_any = BoundClass(PoolWhenAnyEvent)

    #: Return an event triggered when items are put in pool
    when_new = BoundClass(PoolWhenNewEvent)

    #: Return an event triggered when the pool becomes full.
    when_full = BoundClass(PoolWhenFullEvent)

    def _trigger_put(self, _=None):
        if self._putters:
            put_ev = self._putters.pop(0)
            put_ev.succeed()
            self.level += put_ev.amount
            if put_ev.amount:
                self._trigger_when_new()
            self._trigger_when_any()
            self._trigger_when_full()
            if self._put_hook:
                self._put_hook()
        if self.level > self.capacity and self._hard_cap:
            raise OverflowError()

    def _trigger_get(self, _=None):
        if self._getters and self.level:
            for get_ev in self._getters:
                assert get_ev.amount <= self.capacity, (
                    "Amount {} greater than pool's {} capacity {}".format(
                        get_ev.amount, str(self.name), self.capacity))
                if get_ev.amount <= self.level:
                    self._getters.remove(get_ev)
                    self.level -= get_ev.amount
                    get_ev.succeed(get_ev.amount)
                    if self._get_hook:
                        self._get_hook()
                else:
                    break

    def _trigger_when_new(self):
        for when_new_ev in self._new_waiters:
            when_new_ev.succeed()
        del self._new_waiters[:]

    def _trigger_when_any(self):
        if self.level:
            for when_any_ev in self._any_waiters:
                when_any_ev.succeed()
            del self._any_waiters[:]

    def _trigger_when_full(self):
        if self.level >= self.capacity:
            for when_full_ev in self._full_waiters:
                when_full_ev.succeed()
            del self._full_waiters[:]

    def __str__(self):
        return ('Pool: name={0.name}'
                ' level={0.level}'
                ' capacity={0.capacity}'
                ')'.format(self))
