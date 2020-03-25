"""Pool class for modeling a container of resources.

A pool models a container of homogeneous resources, similar to
:class:`simpy.resources.Container`, but with additional events when the
container is empty or full. Resources are :func:`Pool.put` or :func:`Pool.get`
to/from the pool in specified amounts. The pool's resources may be modeled as
either discrete or continuous depending on whether the put/get amounts are
`int` or `float`.
"""

from sys import float_info
import heapq

from simpy import Event
from simpy.core import BoundClass


class PoolPutEvent(Event):
    def __init__(self, pool, amount=1):
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        super(PoolPutEvent, self).__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.callbacks.extend([pool._trigger_when_at_least, pool._trigger_get])
        pool._put_waiters.append(self)
        pool._trigger_put()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()

    def cancel(self):
        if not self.triggered:
            self.pool._put_waiters.remove(self)
            self.callbacks = None


class PoolGetEvent(Event):
    def __init__(self, pool, amount=1):
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        super(PoolGetEvent, self).__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.callbacks.extend([pool._trigger_when_at_most, pool._trigger_put])
        pool._get_waiters.append(self)
        pool._trigger_get()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()

    def cancel(self):
        if not self.triggered:
            self.pool._get_waiters.remove(self)
            self.callbacks = None


class PoolWhenAtMostEvent(Event):
    def __init__(self, pool, amount):
        super(PoolWhenAtMostEvent, self).__init__(pool.env)
        self.pool = pool
        self.amount = amount
        heapq.heappush(pool._at_most_waiters, self)
        pool._trigger_when_at_most()

    def __lt__(self, other):
        return self.amount > other.amount

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()

    def cancel(self):
        if not self.triggered:
            self.pool._at_most_waiters.remove(self)
            heapq.heapify(self.pool._at_most_waiters)
            self.callbacks = None


class PoolWhenAtLeastEvent(Event):
    def __init__(self, pool, amount):
        super(PoolWhenAtLeastEvent, self).__init__(pool.env)
        self.pool = pool
        self.amount = amount
        heapq.heappush(pool._at_least_waiters, self)
        pool._trigger_when_at_least()

    def __lt__(self, other):
        return self.amount < other.amount

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()

    def cancel(self):
        if not self.triggered:
            self.pool._at_least_waiters.remove(self)
            heapq.heapify(self.pool._at_least_waiters)
            self.callbacks = None


class PoolWhenAnyEvent(PoolWhenAtLeastEvent):
    def __init__(self, pool, epsilon=float_info.epsilon):
        super(PoolWhenAnyEvent, self).__init__(pool, amount=epsilon)


class PoolWhenFullEvent(PoolWhenAtLeastEvent):
    def __init__(self, pool):
        super(PoolWhenFullEvent, self).__init__(pool, amount=pool.capacity)


class PoolWhenNotFullEvent(PoolWhenAtMostEvent):
    def __init__(self, pool, epsilon=float_info.epsilon):
        super(PoolWhenNotFullEvent, self).__init__(pool, amount=pool.capacity - epsilon)


class PoolWhenEmptyEvent(PoolWhenAtMostEvent):
    def __init__(self, pool):
        super(PoolWhenEmptyEvent, self).__init__(pool, amount=0)


class Pool:
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

    def __init__(self, env, capacity=float('inf'), init=0, hard_cap=False, name=None):
        self.env = env
        #: Capacity of the pool (maximum level).
        self.capacity = capacity
        #: Current fill level of the pool.
        self.level = init
        self._hard_cap = hard_cap
        self.name = name
        self._put_waiters = []
        self._get_waiters = []
        self._at_most_waiters = []
        self._at_least_waiters = []
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

    #: Return and event triggered when the pool has at least `amount` items.
    when_at_least = BoundClass(PoolWhenAtLeastEvent)

    #: Return and event triggered when the pool has at most `amount` items.
    when_at_most = BoundClass(PoolWhenAtMostEvent)

    #: Return an event triggered when the pool is non-empty.
    when_any = BoundClass(PoolWhenAnyEvent)

    #: Return an event triggered when the pool becomes full.
    when_full = BoundClass(PoolWhenFullEvent)

    #: Return an event triggered when the pool becomes not full.
    when_not_full = BoundClass(PoolWhenNotFullEvent)

    #: Return an event triggered when the pool becomes empty.
    when_empty = BoundClass(PoolWhenEmptyEvent)

    def _trigger_put(self, _=None):
        idx = 0
        while self._put_waiters and idx < len(self._put_waiters):
            put_ev = self._put_waiters[idx]
            if self.capacity - self.level >= put_ev.amount:
                self._put_waiters.pop(idx)
                self.level += put_ev.amount
                put_ev.succeed()
                if self._put_hook:
                    self._put_hook()
            elif self._hard_cap:
                raise OverflowError()
            else:
                idx += 1

    def _trigger_get(self, _=None):
        idx = 0
        while self._get_waiters and idx < len(self._get_waiters):
            get_ev = self._get_waiters[idx]
            if get_ev.amount <= self.level:
                self._get_waiters.pop(idx)
                self.level -= get_ev.amount
                get_ev.succeed(get_ev.amount)
                if self._get_hook:
                    self._get_hook()
            else:
                idx += 1

    def _trigger_when_at_least(self, _=None):
        while self._at_least_waiters and self.level >= self._at_least_waiters[0].amount:
            when_at_least_ev = heapq.heappop(self._at_least_waiters)
            when_at_least_ev.succeed()

    def _trigger_when_at_most(self, _=None):
        while self._at_most_waiters and self.level <= self._at_most_waiters[0].amount:
            at_most_ev = heapq.heappop(self._at_most_waiters)
            at_most_ev.succeed()

    def __repr__(self):
        return (
            f'{self.__class__.__name__}(name={self.name!r} level={self.level}'
            f' capacity={self.capacity})'
        )


class PriorityPoolPutEvent(Event):
    def __init__(self, pool, amount=1, priority=0):
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        super(PriorityPoolPutEvent, self).__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.key = priority, pool._event_count
        pool._event_count += 1
        self.callbacks.extend([pool._trigger_when_at_least, pool._trigger_get])
        heapq.heappush(pool._put_waiters, self)
        pool._trigger_put()

    def __lt__(self, other):
        return self.key < other.key

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()

    def cancel(self):
        if not self.triggered:
            self.pool._put_waiters.remove(self)
            heapq.heapify(self.pool._put_waiters)
            self.callbacks = None


class PriorityPoolGetEvent(Event):
    def __init__(self, pool, amount=1, priority=0):
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        super(PriorityPoolGetEvent, self).__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.key = priority, pool._event_count
        pool._event_count += 1
        self.callbacks.extend([pool._trigger_when_at_most, pool._trigger_put])
        heapq.heappush(pool._get_waiters, self)
        pool._trigger_get()

    def __lt__(self, other):
        return self.key < other.key

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()

    def cancel(self):
        if not self.triggered:
            self.pool._get_waiters.remove(self)
            heapq.heapify(self.pool._get_waiters)
            self.callbacks = None


class PriorityPool(Pool):
    """Pool with prioritizied put() and get() requests.

    A priority is provided with `put()` and `get()` requests. This priority
    determines the strict order in which requests are fulfilled. Requests of
    the same priority are serviced in strict FIFO order.

    """

    def __init__(self, env, capacity=float('inf'), init=0, hard_cap=False, name=None):
        super(PriorityPool, self).__init__(env, capacity, init, hard_cap, name)
        self._event_count = 0

    #: Put amount in the pool.
    put = BoundClass(PriorityPoolPutEvent)

    #: Get amount from the pool.
    get = BoundClass(PriorityPoolGetEvent)

    def _trigger_put(self, _=None):
        while self._put_waiters:
            put_ev = self._put_waiters[0]
            if self.capacity - self.level >= put_ev.amount:
                heapq.heappop(self._put_waiters)
                self.level += put_ev.amount
                put_ev.succeed()
                if self._put_hook:
                    self._put_hook()
            elif self._hard_cap:
                raise OverflowError()
            else:
                break

    def _trigger_get(self, _=None):
        while self._get_waiters:
            get_ev = self._get_waiters[0]
            if get_ev.amount <= self.level:
                heapq.heappop(self._get_waiters)
                self.level -= get_ev.amount
                get_ev.succeed(get_ev.amount)
                if self._get_hook:
                    self._get_hook()
            else:
                break
