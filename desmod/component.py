from .probe import Probe


class Component(object):

    base_name = ''

    def __init__(self, parent, env=None, name=None, index=None):
        assert parent or env
        self.parent = parent
        self.env = parent.env if env is None else env
        self.name = ((self.base_name if name is None else name) +
                     ('' if index is None else str(index)))
        self.index = index
        if parent is None or not parent.scope:
            self.scope = self.name
        else:
            self.scope = self.parent.scope + '.' + self.name
        self.processes = []
        self.children = []
        self.extern_relations = set()
        self.probes = []

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

    def probe(self, name, target=None, **hints):
        if target is None:
            target = getattr(self, name)
        self.probes.append(Probe(self.scope, name, target, **hints))

    def iter_probes(self):
        for probe in self.probes:
            yield probe
        for child in self.children:
            for probe in child.iter_probes():
                yield probe

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
