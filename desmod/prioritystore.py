from collections import namedtuple
from heapq import heappush, heappop

from simpy import Store


class PriorityItem(namedtuple('PriorityItem', 'priority item')):
    def __lt__(self, other):
        return self.priority < other.priority


class PriorityStore(Store):
    def _do_put(self, event):
        if len(self.items) < self._capacity:
            heappush(self.items, event.item)
            event.succeed()

    def _do_get(self, event):
        if self.items:
            event.succeed(heappop(self.items))
