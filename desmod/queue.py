"""Queue classes useful for modeling.

A queue may be used for inter-process message passing, resource pools,
event sequences, and many other modeling applications. The :class:`~Queue`
class implements a simulation-aware, general-purpose queue useful for these
modeling applications.

The :class:`~PriorityQueue` class is an alternative to :class:`~Queue` that
dequeues items in priority-order instead of :class:`Queue`'s FIFO discipline.

"""
from collections import namedtuple
from heapq import heappush, heappop

from simpy import Event
from simpy.core import BoundClass


class QueuePutEvent(Event):
    def __init__(self, queue, item):
        super(QueuePutEvent, self).__init__(queue.env)
        self.queue = queue
        self.item = item
        self.callbacks.append(queue._trigger_get)
        queue._putters.append(self)
        queue._trigger_put()

    def cancel(self):
        if not self.triggered:
            self.queue._putters.remove(self)
            self.callbacks = None


class QueueGetEvent(Event):
    def __init__(self, queue):
        super(QueueGetEvent, self).__init__(queue.env)
        self.queue = queue
        self.callbacks.append(queue._trigger_put)
        queue._getters.append(self)
        queue._trigger_get()

    def cancel(self):
        if not self.triggered:
            self.queue._getters.remove(self)
            self.callbacks = None


class QueueWhenNewEvent(Event):
    def __init__(self, queue):
        super(QueueWhenNewEvent, self).__init__(queue.env)
        self.queue = queue
        queue._new_waiters.append(self)

    def cancel(self):
        if not self.triggered:
            self.queue._new_waiters.remove(self)
            self.callbacks = None


class QueueWhenAnyEvent(Event):
    def __init__(self, queue):
        super(QueueWhenAnyEvent, self).__init__(queue.env)
        self.queue = queue
        queue._any_waiters.append(self)
        queue._trigger_when_any()

    def cancel(self):
        if not self.triggered:
            self.queue._any_waiters.remove(self)
            self.callbacks = None


class QueueWhenFullEvent(Event):
    def __init__(self, queue):
        super(QueueWhenFullEvent, self).__init__(queue.env)
        self.queue = queue
        queue._full_waiters.append(self)
        queue._trigger_when_full()

    def cancel(self):
        if not self.triggered:
            self.queue._full_waiters.remove(self)
            self.callbacks = None


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
        self._putters = []
        self._getters = []
        self._new_waiters = []
        self._any_waiters = []
        self._full_waiters = []
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

    def _enqueue_item(self, item):
        self.items.append(item)

    def _dequeue_item(self):
        return self.items.pop(0)

    def _trigger_put(self, _=None):
        if self._putters:
            if len(self.items) < self.capacity:
                put_ev = self._putters.pop(0)
                put_ev.succeed()
                self._enqueue_item(put_ev.item)
                self._trigger_when_new()
                self._trigger_when_any()
                self._trigger_when_full()
                if self._put_hook:
                    self._put_hook()
            elif self._hard_cap:
                raise OverflowError()

    def _trigger_get(self, _=None):
        if self._getters and self.items:
            get_ev = self._getters.pop(0)
            item = self._dequeue_item()
            get_ev.succeed(item)
            if self._get_hook:
                self._get_hook()

    def _trigger_when_new(self):
        for when_new_ev in self._new_waiters:
            when_new_ev.succeed()
        del self._new_waiters[:]

    def _trigger_when_any(self):
        if self.items:
            for when_any_ev in self._any_waiters:
                when_any_ev.succeed()
            del self._any_waiters[:]

    def _trigger_when_full(self):
        if len(self.items) == self.capacity:
            for when_full_ev in self._full_waiters:
                when_full_ev.succeed()
            del self._full_waiters[:]

    def __str__(self):
        return ('Queue: name={0.name}'
                ' size={1}'
                ' capacity={0.capacity}'
                ')'.format(self, len(self.items)))


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

    def _enqueue_item(self, item):
        heappush(self.items, item)

    def _dequeue_item(self):
        return heappop(self.items)
