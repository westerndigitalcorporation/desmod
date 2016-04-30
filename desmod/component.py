class Component(object):

    base_name = ''

    def __init__(self, parent, env=None, name=None, index=None, tracemgr=None):
        assert parent or (env and tracemgr)
        self.parent = parent
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
        self._connections = set()
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
        self._connections.update(connection_names)

    def connect(self, connection_name, relation):
        setattr(self, connection_name, relation)
        self._connections.remove(connection_name)

    def connect_children(self):
        if any(child._connections for child in self.children):
            raise NotImplementedError(
                '{0} has unconnected children; implement '
                '{0}.connect_children()'.format(type(self).__name__))

    def _check_connections(self):
        if self._connections:
            raise RuntimeError(
                '{scope}.{connection_name} not connected'.format(
                    scope=self.scope,
                    connection_name=self._connections.pop()))

    def auto_probe(self, name, target=None, **hints):
        if target is None:
            target = getattr(self, name)
        target_scope = '.'.join([self.scope, name])
        self.tracemgr.auto_probe(target_scope, target, **hints)

    def get_trace_function(self, name, **hints):
        target_scope = '.'.join([self.scope, name])
        return self.tracemgr.get_trace_function(target_scope, **hints)

    def elaborate(self):
        self.connect_children()
        for child in self.children:
            child._check_connections()
            child.elaborate()
        for proc, args, kwargs in self._processes:
            self.env.process(proc(*args, **kwargs))

    def get_results(self, result):
        for child in self.children:
            child.get_results(result)
        self._get_result(result)

    def _get_result(self, result):
        pass
