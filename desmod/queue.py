"""Queue classes useful for modeling.

A queue may be used for inter-process message passing, resource pools,
event sequences, and many other modeling applications. The :class:`~Queue`
class implements a simulation-aware, general-purpose queue useful for these
modeling applications.

The :class:`~PriorityQueue` class is an alternative to :class:`~Queue` that
dequeues items in priority-order instead of :class:`Queue`'s FIFO discipline.

"""
from collections import namedtuple
from heapq import heapify, heappop, heappush

from simpy import Event
from simpy.core import BoundClass


class QueueEvent(Event):
    def __init__(self, queue):
        super(QueueEvent, self).__init__(queue.env)
        self.queue = queue
        queue._waiters.setdefault(type(self), []).append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()

    def cancel(self):
        if not self.triggered:
            self.queue._waiters[type(self)].remove(self)
            self.callbacks = None


class QueuePutEvent(QueueEvent):
    def __init__(self, queue, item):
        self.item = item
        super(QueuePutEvent, self).__init__(queue)
        self.callbacks.extend(
            [
                queue._trigger_when_full,
                queue._trigger_when_new,
                queue._trigger_when_any,
                queue._trigger_get,
            ]
        )
        queue._trigger_put()


class QueueGetEvent(QueueEvent):
    def __init__(self, queue):
        super(QueueGetEvent, self).__init__(queue)
        self.callbacks.extend(
            [
                queue._trigger_when_not_full,
                queue._trigger_put,
            ]
        )
        queue._trigger_get()


class QueueWhenNewEvent(QueueEvent):
    pass


class QueueWhenAnyEvent(QueueEvent):
    def __init__(self, queue):
        super(QueueWhenAnyEvent, self).__init__(queue)
        queue._trigger_when_any()


class QueueWhenFullEvent(QueueEvent):
    def __init__(self, queue):
        super(QueueWhenFullEvent, self).__init__(queue)
        queue._trigger_when_full()


class QueueWhenNotFullEvent(QueueEvent):
    def __init__(self, queue):
        super(QueueWhenNotFullEvent, self).__init__(queue)
        queue._trigger_when_not_full()


class Queue(object):
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
    def __init__(self, env, capacity=float('inf'), hard_cap=False, items=(),
                 name=None):
        self.env = env
        #: Capacity of the queue (maximum number of items).
        self.capacity = capacity
        self._hard_cap = hard_cap
        self.items = list(items)
        self.name = name
        self._waiters = {}
        self._put_hook = None
        self._get_hook = None
        BoundClass.bind_early(self)

    @property
    def size(self):
        """Number of items in queue."""
        return len(self.items)

    @property
    def remaining(self):
        """Remaining queue capacity."""
        return self.capacity - len(self.items)

    @property
    def is_empty(self):
        """Indicates whether the queue is empty."""
        return not self.items

    @property
    def is_full(self):
        """Indicates whether the queue is full."""
        return len(self.items) >= self.capacity

    def peek(self):
        """Peek at the next item in the queue."""
        return self.items[0]

    #: Enqueue an item on the queue.
    put = BoundClass(QueuePutEvent)

    #: Dequeue an item from the queue.
    get = BoundClass(QueueGetEvent)

    #: Return an event triggered when a new item is put into the queue.
    when_new = BoundClass(QueueWhenNewEvent)

    #: Return an event triggered when the queue is non-empty.
    when_any = BoundClass(QueueWhenAnyEvent)

    #: Return an event triggered when the queue becomes full.
    when_full = BoundClass(QueueWhenFullEvent)

    #: Return an event triggered when the queue becomes not full.
    when_not_full = BoundClass(QueueWhenNotFullEvent)

    def _enqueue_item(self, item):
        self.items.append(item)

    def _dequeue_item(self):
        return self.items.pop(0)

    def _trigger_put(self, _=None):
        waiters = self._waiters.get(QueuePutEvent)
        while waiters:
            if len(self.items) < self.capacity:
                put_ev = waiters.pop(0)
                self._enqueue_item(put_ev.item)
                put_ev.succeed()
                if self._put_hook:
                    self._put_hook()
            elif self._hard_cap:
                raise OverflowError()
            else:
                break

    def _trigger_get(self, _=None):
        waiters = self._waiters.get(QueueGetEvent)
        while waiters and self.items:
            get_ev = waiters.pop(0)
            item = self._dequeue_item()
            get_ev.succeed(item)
            if self._get_hook:
                self._get_hook()

    def _trigger_when_new(self, _=None):
        waiters = self._waiters.get(QueueWhenNewEvent)
        if waiters:
            for when_new_ev in waiters:
                when_new_ev.succeed()
            del waiters[:]

    def _trigger_when_any(self, _=None):
        waiters = self._waiters.get(QueueWhenAnyEvent)
        if waiters and self.items:
            for when_any_ev in waiters:
                when_any_ev.succeed()
            del waiters[:]

    def _trigger_when_full(self, _=None):
        waiters = self._waiters.get(QueueWhenFullEvent)
        if waiters and self.is_full:
            for when_full_ev in waiters:
                when_full_ev.succeed()
            del waiters[:]

    def _trigger_when_not_full(self, _=None):
        waiters = self._waiters.get(QueueWhenNotFullEvent)
        if waiters and not self.is_full:
            for when_not_full_ev in waiters:
                when_not_full_ev.succeed()
            del waiters[:]

    def __repr__(self):
        return (
            '{0.__class__.__name__}(name={0.name!r} size={0.size}'
            ' capacity={0.capacity})'
        ).format(self)


class PriorityItem(namedtuple('PriorityItem', 'priority item')):
    """Wrap items with explicit priority for use with :class:`~PriorityQueue`.

    :param priority:
        Orderable priority value. Smaller values are dequeued first.
    :param item:
        Arbitrary item. Only the `priority` is determines dequeue order, so the
        `item` itself does not have to be orderable.

    """
    def __lt__(self, other):
        return self.priority < other.priority


class PriorityQueue(Queue):
    """Specialized queue where items are dequeued in priority order.

    Items in `PriorityQueue` must be orderable (implement
    :meth:`~object.__lt__`). Unorderable items may be used with `PriorityQueue`
    by wrapping with :class:`~PriorityItem`.

    Items that evaluate less-than other items will be dequeued first.

    """

    def __init__(self, *args, **kwargs):
        super(PriorityQueue, self).__init__(*args, **kwargs)
        heapify(self.items)

    def _enqueue_item(self, item):
        heappush(self.items, item)

    def _dequeue_item(self):
        return heappop(self.items)
