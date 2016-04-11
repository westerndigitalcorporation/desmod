import simpy


class MessageQueue(object):

    store_type = simpy.Store

    def __init__(self, env, capacity=float('inf'), send_time=0, recv_time=0):
        assert send_time >= 0
        assert recv_time >= 0
        self.env = env
        self.send_time = send_time
        self.recv_time = recv_time
        self._store = self.store_type(env, capacity)
        self._slots = simpy.Resource(env, capacity)

    def send(self, item):
        return self.env.process(self._send_process(item))

    def _send_process(self, item):
        yield self._slots.request()
        if self.send_time:
            yield self.env.timeout(self.send_time)
        yield self._store.put(item)

    def recv(self):
        return self.env.process(self._recv_process())

    def _recv_process(self):
        item = yield self._store.get()
        if self.recv_time:
            yield self.env.timeout(self.recv_time)
        yield self._slots.release(self._slots.users[0])
        self.env.exit(item)


if hasattr(simpy, 'PriorityStore'):
    class PriorityMessageQueue(MessageQueue):

        store_type = simpy.PriorityStore


class MessageQueue2(simpy.Store):

    def __init__(self, env, capacity=float('inf'), put_time=0, get_time=0):
        super(MessageQueue2, self).__init__(env, capacity)
        assert put_time >= 0
        assert get_time >= 0
        self.put_time = put_time
        self.get_time = get_time
        if capacity < float('inf'):
            self._slots = simpy.Resource(env, capacity)
        else:
            self._slots = None

    def put(self, item):
        return self._env.process(self._put_process(item))

    def _put_process(self, item):
        if self._slots:
            yield self._slots.request()
        if self.put_time:
            yield self._env.timeout(self.put_time)
        yield super(MessageQueue2, self).put(item)

    def get(self):
        return self._env.process(self._get_process())

    def _get_process(self):
        item = yield super(MessageQueue2, self).get()
        if self.get_time:
            yield self._env.timeout(self.get_time)
        if self._slots:
            yield self._slots.release(self._slots.users[0])
        self._env.exit(item)


class FugitiveMessageQueue(object):
    pass


class RendezvousMessageQueue(object):
    pass
