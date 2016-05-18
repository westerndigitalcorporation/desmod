class Component(object):

    base_name = ''

    def __init__(self, parent, env=None, name=None, index=None, tracemgr=None):
        assert parent or (env and tracemgr)
        self.env = parent.env if env is None else env
        self.tracemgr = parent.tracemgr if tracemgr is None else tracemgr
        self.name = ((self.base_name if name is None else name) +
                     ('' if index is None else str(index)))
        self.index = index
        if parent is None or not parent.scope:
            self.scope = self.name
        else:
            self.scope = parent.scope + '.' + self.name
        self._processes = []
        self._connections = []
        self._not_connected = set()
        self.children = []

        self.error = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'ERROR'})
        self.warn = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'WARNING'})
        self.info = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'INFO'})
        self.debug = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'DEBUG'})

    def add_process(self, process_func, *args, **kwargs):
        self._processes.append((process_func, args, kwargs))

    def add_processes(self, *process_funcs):
        for process_func in process_funcs:
            self.add_process(process_func)

    def add_connections(self, *connection_names):
        self._not_connected.update(connection_names)

    def connect(self, dst, dst_connection, src=None, src_connection=None,
                conn_obj=None):
        if src is None:
            src = self
        if src_connection is None:
            src_connection = dst_connection
        if conn_obj is None:
            conn_obj = getattr(src, src_connection)
        setattr(dst, dst_connection, conn_obj)
        dst._not_connected.remove(dst_connection)
        dst._connections.append(
            (dst_connection, src, src_connection, conn_obj))

    def connect_children(self):
        if any(child._not_connected for child in self.children):
            raise NotImplementedError(
                '{0} has unconnected children; implement '
                '{0}.connect_children()'.format(type(self).__name__))

    def auto_probe(self, name, target=None, **hints):
        if target is None:
            target = getattr(self, name)
        target_scope = '.'.join([self.scope, name])
        self.tracemgr.auto_probe(target_scope, target, **hints)

    def get_trace_function(self, name, **hints):
        target_scope = '.'.join([self.scope, name])
        return self.tracemgr.get_trace_function(target_scope, **hints)

    @classmethod
    def pre_init(cls, env):
        pass

    def elaborate(self):
        self.connect_children()
        for child in self.children:
            if child._not_connected:
                raise RuntimeError('{scope}.{conn_name} not connected'.format(
                    scope=child.scope, conn_name=child._not_connected.pop()))
            child.elaborate()
        for proc, args, kwargs in self._processes:
            self.env.process(proc(*args, **kwargs))
        self.elab_hook()

    def elab_hook(self):
        pass

    def post_simulate(self):
        for child in self.children:
            child.post_simulate()
        self.post_sim_hook()

    def post_sim_hook(self):
        pass

    def get_result(self, result):
        for child in self.children:
            child.get_result(result)
        self.get_result_hook(result)

    def get_result_hook(self, result):
        pass
