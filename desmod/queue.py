"""Queue classes useful for modeling.

A queue may be used for inter-process message passing, resource pools,
event sequences, and many other modeling applications. The :class:`~Queue`
class implements a simulation-aware, general-purpose queue useful for these
modeling applications.

The :class:`~PriorityQueue` class is an alternative to :class:`~Queue` that
dequeues items in priority-order instead of :class:`Queue`'s FIFO discipline.

"""
from heapq import heapify, heappop, heappush
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Type,
    TypeVar,
    Union,
)

from simpy.core import BoundClass, Environment
from simpy.events import Event

EventCallback = Callable[[Event], None]


class QueuePutEvent(Event):
    callbacks: List[EventCallback]

    def __init__(self, queue: 'Queue[ItemType]', item: Any) -> None:
        super().__init__(queue.env)
        self.queue = queue
        self.item = item
        queue._put_waiters.append(self)
        self.callbacks.extend([queue._trigger_when_at_least, queue._trigger_get])
        queue._trigger_put()

    def __enter__(self) -> 'QueuePutEvent':
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
            self.queue._put_waiters.remove(self)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class QueueGetEvent(Event):
    callbacks: List[EventCallback]

    def __init__(self, queue: 'Queue[ItemType]') -> None:
        super().__init__(queue.env)
        self.queue = queue
        queue._get_waiters.append(self)
        self.callbacks.extend([queue._trigger_when_at_most, queue._trigger_put])
        queue._trigger_get()

    def __enter__(self) -> 'QueueGetEvent':
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
            self.queue._get_waiters.remove(self)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class QueueWhenAtMostEvent(Event):
    def __init__(self, queue: 'Queue[ItemType]', num_items: Union[int, float]) -> None:
        super().__init__(queue.env)
        self.queue = queue
        self.num_items = num_items
        heappush(queue._at_most_waiters, self)
        queue._trigger_when_at_most()

    def __lt__(self, other: 'QueueWhenAtMostEvent') -> bool:
        return self.num_items > other.num_items

    def __enter__(self) -> 'QueueWhenAtMostEvent':
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
            self.queue._at_most_waiters.remove(self)
            heapify(self.queue._at_most_waiters)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class QueueWhenAtLeastEvent(Event):
    def __init__(self, queue: 'Queue[ItemType]', num_items: Union[int, float]) -> None:
        super().__init__(queue.env)
        self.queue = queue
        self.num_items = num_items
        heappush(queue._at_least_waiters, self)
        queue._trigger_when_at_least()

    def __lt__(self, other: 'QueueWhenAtLeastEvent') -> bool:
        return self.num_items < other.num_items

    def __enter__(self) -> 'QueueWhenAtLeastEvent':
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
            self.queue._at_least_waiters.remove(self)
            heapify(self.queue._at_least_waiters)
            self.callbacks = None  # type: ignore[assignment] # noqa: F821


class QueueWhenAnyEvent(QueueWhenAtLeastEvent):
    def __init__(self, queue: 'Queue[ItemType]') -> None:
        super().__init__(queue, num_items=1)


class QueueWhenFullEvent(QueueWhenAtLeastEvent):
    def __init__(self, queue: 'Queue[ItemType]') -> None:
        super().__init__(queue, num_items=queue.capacity)


class QueueWhenNotFullEvent(QueueWhenAtMostEvent):
    def __init__(self, queue: 'Queue[ItemType]') -> None:
        super().__init__(queue, num_items=queue.capacity - 1)


class QueueWhenEmptyEvent(QueueWhenAtMostEvent):
    def __init__(self, queue: 'Queue[ItemType]') -> None:
        super().__init__(queue, num_items=0)


ItemType = TypeVar('ItemType')


class Queue(Generic[ItemType]):
    """Simulation queue of arbitrary items.

    `Queue` is similar to :class:`simpy.Store`. It provides a simulation-aware
    first-in first-out (FIFO) queue useful for passing messages between
    simulation processes or managing a pool of objects needed by multiple
    processes.

    Items are enqueued and dequeued using :meth:`put()` and :meth:`get()`.

    :param env: Simulation environment.
    :param capacity: Capacity of the queue; infinite by default.
    :param hard_cap:
        If specified, the queue overflows when the `capacity` is reached.
    :param items: Optional sequence of items to pre-populate the queue.
    :param name: Optional name to associate with the queue.

    """

    def __init__(
        self,
        env: Environment,
        capacity: Union[int, float] = float('inf'),
        hard_cap: bool = False,
        items: Iterable[ItemType] = (),
        name: Optional[str] = None,
    ) -> None:
        self.env = env
        #: Capacity of the queue (maximum number of items).
        self.capacity = capacity
        self._hard_cap = hard_cap
        self.items: List[ItemType] = list(items)
        self.name = name
        self._put_waiters: List[QueuePutEvent] = []
        self._get_waiters: List[QueueGetEvent] = []
        self._at_most_waiters: List[QueueWhenAtMostEvent] = []
        self._at_least_waiters: List[QueueWhenAtLeastEvent] = []
        self._put_hook: Optional[Callable[[], Any]] = None
        self._get_hook: Optional[Callable[[], Any]] = None
        BoundClass.bind_early(self)

    @property
    def size(self) -> int:
        """Number of items in queue."""
        return len(self.items)

    @property
    def remaining(self) -> Union[int, float]:
        """Remaining queue capacity."""
        return self.capacity - len(self.items)

    @property
    def is_empty(self) -> bool:
        """Indicates whether the queue is empty."""
        return not self.items

    @property
    def is_full(self) -> bool:
        """Indicates whether the queue is full."""
        return len(self.items) >= self.capacity

    def peek(self) -> ItemType:
        """Peek at the next item in the queue."""
        return self.items[0]

    if TYPE_CHECKING:

        def put(self, item: ItemType) -> QueuePutEvent:
            """Enqueue an item on the queue."""
            ...

        def get(self) -> QueueGetEvent:
            """Dequeue an item from the queue."""
            ...

        def when_at_least(self, num_items: int) -> QueueWhenAtLeastEvent:
            """Return an event triggered when the queue has at least n items."""
            ...

        def when_at_most(self, num_items: int) -> QueueWhenAtMostEvent:
            """Return an event triggered when the queue has at most n items."""
            ...

        def when_any(self) -> QueueWhenAnyEvent:
            """Return an event triggered when the queue is non-empty."""
            ...

        def when_full(self) -> QueueWhenFullEvent:
            """Return an event triggered when the queue becomes full."""
            ...

        def when_not_full(self) -> QueueWhenNotFullEvent:
            """Return an event triggered when the queue becomes not full."""
            ...

        def when_empty(self) -> QueueWhenEmptyEvent:
            """Return an event triggered when the queue becomes empty."""
            ...

    else:
        put = BoundClass(QueuePutEvent)
        get = BoundClass(QueueGetEvent)
        when_at_least = BoundClass(QueueWhenAtLeastEvent)
        when_at_most = BoundClass(QueueWhenAtMostEvent)
        when_any = BoundClass(QueueWhenAnyEvent)
        when_full = BoundClass(QueueWhenFullEvent)
        when_not_full = BoundClass(QueueWhenNotFullEvent)
        when_empty = BoundClass(QueueWhenEmptyEvent)

    def _enqueue_item(self, item: ItemType) -> None:
        self.items.append(item)

    def _dequeue_item(self) -> ItemType:
        return self.items.pop(0)

    def _trigger_put(self, _: Optional[Event] = None) -> None:
        while self._put_waiters:
            if len(self.items) < self.capacity:
                put_ev = self._put_waiters.pop(0)
                self._enqueue_item(put_ev.item)
                put_ev.succeed()
                if self._put_hook:
                    self._put_hook()
            elif self._hard_cap:
                raise OverflowError()
            else:
                break

    def _trigger_get(self, _: Optional[Event] = None) -> None:
        while self._get_waiters and self.items:
            get_ev = self._get_waiters.pop(0)
            item = self._dequeue_item()
            get_ev.succeed(item)
            if self._get_hook:
                self._get_hook()

    def _trigger_when_at_least(self, _: Optional[Event] = None) -> None:
        while (
            self._at_least_waiters and self.size >= self._at_least_waiters[0].num_items
        ):
            when_at_least_ev = heappop(self._at_least_waiters)
            when_at_least_ev.succeed()

    def _trigger_when_at_most(self, _: Optional[Event] = None) -> None:
        while self._at_most_waiters and self.size <= self._at_most_waiters[0].num_items:
            at_most_ev = heappop(self._at_most_waiters)
            at_most_ev.succeed()

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}('
            f'name={self.name!r} size={self.size} capacity={self.capacity})'
        )


class PriorityItem(NamedTuple):
    """Wrap items with explicit priority for use with :class:`~PriorityQueue`.

    :param priority:
        Orderable priority value. Smaller values are dequeued first.
    :param item:
        Arbitrary item. Only the `priority` is determines dequeue order, so the
        `item` itself does not have to be orderable.

    """

    priority: Any
    item: Any

    def __lt__(  # type: ignore[override] # noqa: F821
        self, other: 'PriorityItem'
    ) -> bool:
        return self.priority < other.priority


class PriorityQueue(Queue[ItemType]):
    """Specialized queue where items are dequeued in priority order.

    Items in `PriorityQueue` must be orderable (implement
    :meth:`~object.__lt__`). Unorderable items may be used with `PriorityQueue`
    by wrapping with :class:`~PriorityItem`.

    Items that evaluate less-than other items will be dequeued first.

    """

    def __init__(
        self,
        env: Environment,
        capacity: Union[int, float] = float('inf'),
        hard_cap: bool = False,
        items: Iterable[ItemType] = (),
        name: Optional[str] = None,
    ) -> None:
        super().__init__(env, capacity, hard_cap, items, name)
        heapify(self.items)

    def _enqueue_item(self, item: ItemType) -> None:
        heappush(self.items, item)

    def _dequeue_item(self) -> ItemType:
        return heappop(self.items)
