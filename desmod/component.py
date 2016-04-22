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
        self.processes = []
        self.children = []
        self.extern_relations = set()

        self.error = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'ERROR'})
        self.warn = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'WARNING'})
        self.info = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'INFO'})
        self.debug = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'DEBUG'})

    def connect(self, relation_name, relation):
        setattr(self, relation_name, relation)
        self.extern_relations.remove(relation_name)

    def connect_children(self):
        pass

    def _check_connections(self):
        if self.extern_relations:
            raise RuntimeError('{scope}.{relation_name} not connected'.format(
                scope=self.scope,
                relation_name=self.extern_relations.pop()))

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
        for proc in self.processes:
            self.env.process(proc())

    def get_results(self, result):
        for child in self.children:
            child.get_results(result)
        self._get_result(result)

    def _get_result(self, result):
        pass
