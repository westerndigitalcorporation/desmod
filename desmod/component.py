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

        log_tracer = self.tracemgr.log_tracer
        self.error = log_tracer.get_log_function(self.scope, 'ERROR')
        self.warn = log_tracer.get_log_function(self.scope, 'WARNING')
        self.info = log_tracer.get_log_function(self.scope, 'INFO')
        self.debug = log_tracer.get_log_function(self.scope, 'DEBUG')

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

    def elaborate(self):
        self.connect_children()
        for child in self.children:
            child._check_connections()
            child.elaborate()

    def simulate(self):
        for child in self.children:
            child.simulate()
        for proc in self.processes:
            self.env.process(proc())
