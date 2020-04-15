"""Pool class for modeling a container of resources.

A pool models a container of homogeneous resources, similar to
:class:`simpy.resources.Container`, but with additional events when the
container is empty or full. Resources are :func:`Pool.put` or :func:`Pool.get`
to/from the pool in specified amounts. The pool's resources may be modeled as
either discrete or continuous depending on whether the put/get amounts are
`int` or `float`.
"""

from heapq import heapify, heappop, heappush
from sys import float_info
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Type, Union

from simpy.core import BoundClass, Environment
from simpy.events import Event

EventCallback = Callable[[Event], None]
PoolAmount = Union[int, float]


class PoolPutEvent(Event):
    callbacks: List[EventCallback]

    def __init__(self, pool: 'Pool', amount: PoolAmount = 1) -> None:
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        super().__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.callbacks.extend([pool._trigger_when_at_least, pool._trigger_get])
        pool._put_waiters.append(self)
        pool._trigger_put()

    def __enter__(self) -> 'PoolPutEvent':
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self.cancel()
        return None

    def cancel(self) -> None:
        if not self.triggered:
            self.pool._put_waiters.remove(self)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class PoolGetEvent(Event):
    callbacks: List[EventCallback]

    def __init__(self, pool: 'Pool', amount: PoolAmount = 1) -> None:
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        super().__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.callbacks.extend([pool._trigger_when_at_most, pool._trigger_put])
        pool._get_waiters.append(self)
        pool._trigger_get()

    def __enter__(self) -> 'PoolGetEvent':
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self.cancel()
        return None

    def cancel(self) -> None:
        if not self.triggered:
            self.pool._get_waiters.remove(self)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class PoolWhenAtMostEvent(Event):
    def __init__(self, pool: 'Pool', amount: PoolAmount) -> None:
        super().__init__(pool.env)
        self.pool = pool
        self.amount = amount
        heappush(pool._at_most_waiters, self)
        pool._trigger_when_at_most()

    def __lt__(self, other: 'PoolWhenAtMostEvent') -> bool:
        return self.amount > other.amount

    def __enter__(self) -> 'PoolWhenAtMostEvent':
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self.cancel()
        return None

    def cancel(self) -> None:
        if not self.triggered:
            self.pool._at_most_waiters.remove(self)
            heapify(self.pool._at_most_waiters)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class PoolWhenAtLeastEvent(Event):
    def __init__(self, pool: 'Pool', amount: PoolAmount) -> None:
        super().__init__(pool.env)
        self.pool = pool
        self.amount = amount
        heappush(pool._at_least_waiters, self)
        pool._trigger_when_at_least()

    def __lt__(self, other: 'PoolWhenAtLeastEvent') -> bool:
        return self.amount < other.amount

    def __enter__(self) -> 'PoolWhenAtLeastEvent':
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self.cancel()
        return None

    def cancel(self) -> None:
        if not self.triggered:
            self.pool._at_least_waiters.remove(self)
            heapify(self.pool._at_least_waiters)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class PoolWhenAnyEvent(PoolWhenAtLeastEvent):
    def __init__(self, pool: 'Pool', epsilon: float = float_info.min):
        super().__init__(pool, amount=epsilon)


class PoolWhenFullEvent(PoolWhenAtLeastEvent):
    def __init__(self, pool: 'Pool'):
        super().__init__(pool, amount=pool.capacity)


class PoolWhenNotFullEvent(PoolWhenAtMostEvent):
    def __init__(self, pool: 'Pool', epsilon: Optional[float] = None):
        if epsilon is None and isinstance(pool.capacity, int):
            epsilon = 0.5
        assert epsilon is not None, "when_not_any(epsilon) is required for float Pool."
        super().__init__(pool, amount=pool.capacity - epsilon)


class PoolWhenEmptyEvent(PoolWhenAtMostEvent):
    def __init__(self, pool: 'Pool'):
        super().__init__(pool, amount=0)


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

    def __init__(
        self,
        env: Environment,
        capacity: PoolAmount = float('inf'),
        init: PoolAmount = 0,
        hard_cap: bool = False,
        name: Optional[str] = None,
    ):
        self.env = env
        #: Capacity of the pool (maximum level).
        self.capacity = capacity
        #: Current fill level of the pool.
        self.level = init
        self._hard_cap = hard_cap
        self.name = name
        self._put_waiters: List[PoolPutEvent] = []
        self._get_waiters: List[PoolGetEvent] = []
        self._at_most_waiters: List[PoolWhenAtMostEvent] = []
        self._at_least_waiters: List[PoolWhenAtLeastEvent] = []
        self._put_hook: Optional[Callable[[], Any]] = None
        self._get_hook: Optional[Callable[[], Any]] = None
        BoundClass.bind_early(self)

    @property
    def remaining(self) -> PoolAmount:
        """Remaining pool capacity."""
        return self.capacity - self.level

    @property
    def is_empty(self) -> bool:
        """Indicates whether the pool is empty."""
        return self.level == 0

    @property
    def is_full(self) -> bool:
        """Indicates whether the pool is full."""
        return self.level >= self.capacity

    if TYPE_CHECKING:

        def put(self, amount: PoolAmount = 1) -> PoolPutEvent:
            """Put amount in the pool."""
            ...

        def get(self, amount: PoolAmount = 1) -> PoolGetEvent:
            """Get amount from the pool."""
            ...

        def when_at_least(self, amount: PoolAmount) -> PoolWhenAtLeastEvent:
            """Return an event triggered when the pool has at least `amount` items."""
            ...

        def when_at_most(self, amount: PoolAmount) -> PoolWhenAtMostEvent:
            """Return an event triggered when the pool has at most `amount` items."""
            ...

        def when_any(self, epsilon: float = ...) -> PoolWhenAnyEvent:
            """Return an event triggered when the pool is non-empty."""
            ...

        def when_full(self) -> PoolWhenFullEvent:
            """Return an event triggered when the pool becomes full."""
            ...

        def when_not_full(self, epsilon: float = ...) -> PoolWhenNotFullEvent:
            """Return an event triggered when the pool becomes not full."""
            ...

        def when_empty(self) -> PoolWhenEmptyEvent:
            """Return an event triggered when the pool becomes empty."""
            ...

    else:
        put = BoundClass(PoolPutEvent)
        get = BoundClass(PoolGetEvent)
        when_at_least = BoundClass(PoolWhenAtLeastEvent)
        when_at_most = BoundClass(PoolWhenAtMostEvent)
        when_any = BoundClass(PoolWhenAnyEvent)
        when_full = BoundClass(PoolWhenFullEvent)
        when_not_full = BoundClass(PoolWhenNotFullEvent)
        when_empty = BoundClass(PoolWhenEmptyEvent)

    def _trigger_put(self, _: Optional[Event] = None) -> None:
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

    def _trigger_get(self, _: Optional[Event] = None) -> None:
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

    def _trigger_when_at_least(self, _: Optional[Event] = None) -> None:
        while self._at_least_waiters and self.level >= self._at_least_waiters[0].amount:
            when_at_least_ev = heappop(self._at_least_waiters)
            when_at_least_ev.succeed()

    def _trigger_when_at_most(self, _: Optional[Event] = None) -> None:
        while self._at_most_waiters and self.level <= self._at_most_waiters[0].amount:
            at_most_ev = heappop(self._at_most_waiters)
            at_most_ev.succeed()

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}(name={self.name!r} level={self.level}'
            f' capacity={self.capacity})'
        )


class PriorityPoolPutEvent(Event):
    callbacks: List[EventCallback]

    def __init__(
        self, pool: 'PriorityPool', amount: PoolAmount = 1, priority: int = 0
    ) -> None:
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        super().__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.key = priority, pool._event_count
        pool._event_count += 1
        self.callbacks.extend([pool._trigger_when_at_least, pool._trigger_get])
        heappush(pool._put_waiters, self)
        pool._trigger_put()

    def __lt__(self, other: 'PriorityPoolPutEvent') -> bool:
        return self.key < other.key

    def __enter__(self) -> 'PriorityPoolPutEvent':
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self.cancel()
        return None

    def cancel(self) -> None:
        if not self.triggered:
            self.pool._put_waiters.remove(self)
            heapify(self.pool._put_waiters)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class PriorityPoolGetEvent(Event):
    callbacks: List[EventCallback]

    def __init__(self, pool: 'PriorityPool', amount: PoolAmount = 1, priority: int = 0):
        if not (0 < amount <= pool.capacity):
            raise ValueError('amount must be in (0, capacity]')
        super().__init__(pool.env)
        self.pool = pool
        self.amount = amount
        self.key = priority, pool._event_count
        pool._event_count += 1
        self.callbacks.extend([pool._trigger_when_at_most, pool._trigger_put])
        heappush(pool._get_waiters, self)
        pool._trigger_get()

    def __lt__(self, other: 'PriorityPoolGetEvent') -> bool:
        return self.key < other.key

    def __enter__(self) -> 'PriorityPoolGetEvent':
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self.cancel()
        return None

    def cancel(self) -> None:
        if not self.triggered:
            self.pool._get_waiters.remove(self)
            heapify(self.pool._get_waiters)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class PriorityPool(Pool):
    """Pool with prioritizied put() and get() requests.

    A priority is provided with `put()` and `get()` requests. This priority
    determines the strict order in which requests are fulfilled. Requests of
    the same priority are serviced in strict FIFO order.

    """

    _put_waiters: List[PriorityPoolPutEvent]  # type: ignore[assignment] # noqa: F821
    _get_waiters: List[PriorityPoolGetEvent]  # type: ignore[assignment] # noqa: F821

    def __init__(
        self,
        env: Environment,
        capacity: PoolAmount = float('inf'),
        init: PoolAmount = 0,
        hard_cap: bool = False,
        name: Optional[str] = None,
    ):
        super().__init__(env, capacity, init, hard_cap, name)
        self._event_count = 0

    if TYPE_CHECKING:

        def put(  # type: ignore[override] # noqa: F821
            self, amount: PoolAmount = 1, priority: int = 0
        ) -> PriorityPoolPutEvent:
            """Put amount in the pool."""
            ...

        def get(  # type: ignore[override] # noqa: F821
            self, amount: PoolAmount = 1, priority: int = 0
        ) -> PriorityPoolGetEvent:
            """Get amount from the pool."""
            ...

    else:
        put = BoundClass(PriorityPoolPutEvent)
        get = BoundClass(PriorityPoolGetEvent)

    def _trigger_put(self, _: Optional[Event] = None) -> None:
        while self._put_waiters:
            put_ev = self._put_waiters[0]
            if self.capacity - self.level >= put_ev.amount:
                heappop(self._put_waiters)
                self.level += put_ev.amount
                put_ev.succeed()
                if self._put_hook:
                    self._put_hook()
            elif self._hard_cap:
                raise OverflowError()
            else:
                break

    def _trigger_get(self, _: Optional[Event] = None) -> None:
        while self._get_waiters:
            get_ev = self._get_waiters[0]
            if get_ev.amount <= self.level:
                heappop(self._get_waiters)
                self.level -= get_ev.amount
                get_ev.succeed(get_ev.amount)
                if self._get_hook:
                    self._get_hook()
            else:
                break
