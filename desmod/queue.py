from collections import namedtuple
from heapq import heappush, heappop

from simpy import Event
from simpy.core import BoundClass


class QueuePutEvent(Event):
    def __init__(self, queue, item):
        super(QueuePutEvent, self).__init__(queue.env)
        self.item = item
        self.callbacks.append(queue._trigger_get)
        queue._putters.append(self)
        queue._trigger_put()


class QueueGetEvent(Event):
    def __init__(self, queue):
        super(QueueGetEvent, self).__init__(queue.env)
        self.callbacks.append(queue._trigger_put)
        queue._getters.append(self)
        queue._trigger_get()


class QueueWhenAnyEvent(Event):
    def __init__(self, queue):
        super(QueueWhenAnyEvent, self).__init__(queue.env)
        queue._any_waiters.append(self)
        queue._trigger_when_any()


class QueueWhenFullEvent(Event):
    def __init__(self, queue):
        super(QueueWhenFullEvent, self).__init__(queue.env)
        queue._full_waiters.append(self)
        queue._trigger_when_full()


class Queue(object):
    def __init__(self, env, capacity=float('inf'), hard_cap=False, items=()):
        self.env = env
        self.capacity = capacity
        self._hard_cap = hard_cap
        self.items = list(items)
        self._putters = []
        self._getters = []
        self._any_waiters = []
        self._full_waiters = []
        self._put_hook = None
        self._get_hook = None
        BoundClass.bind_early(self)

    @property
    def is_empty(self):
        return not self.items

    @property
    def is_full(self):
        return len(self.items) >= self.capacity

    def peek(self):
        return self.items[0]

    put = BoundClass(QueuePutEvent)
    get = BoundClass(QueueGetEvent)
    when_any = BoundClass(QueueWhenAnyEvent)
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


class PriorityItem(namedtuple('PriorityItem', 'priority item')):
    def __lt__(self, other):
        return self.priority < other.priority


class PriorityQueue(Queue):
    def _enqueue_item(self, item):
        heappush(self.items, item)

    def _dequeue_item(self):
        return heappop(self.items)
