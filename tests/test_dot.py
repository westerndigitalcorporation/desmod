import pytest

from desmod.dot import component_to_dot
from desmod.component import Component
from desmod.simulation import SimEnvironment


@pytest.fixture
def top():
    top = Top(parent=None, env=SimEnvironment(config={}))
    top.elaborate()
    return top


class Top(Component):
    base_name = ''

    def __init__(self, *args, **kwargs):
        super(Top, self).__init__(*args, **kwargs)
        self.a = A(self)
        self.bs = [B(self, index=i) for i in range(5)]

    def connect_children(self):
        for b in self.bs:
            self.connect(b, 'a')


class A(Component):
    base_name = 'a'


class B(Component):
    base_name = 'b'

    def __init__(self, *args, **kwargs):
        super(B, self).__init__(*args, **kwargs)
        self.add_connections('a')
        self.add_process(self.my_proc)

    def my_proc(self):
        yield self.env.timeout(1)  # pragma: no coverage


def test_hierarchy_only(top):
    dot = component_to_dot(top, show_connections=False, show_processes=False)
    assert '"a"' in dot
    assert '"b0"' in dot


def test_connections_only(top):
    dot = component_to_dot(top, show_hierarchy=False, show_processes=False)
    assert '"b0" -> "a"' in dot


def test_processes_only(top):
    dot = component_to_dot(top, show_hierarchy=False, show_connections=False)
    assert 'my_proc' in dot


def test_all(top):
    dot = component_to_dot(top, colorscheme='blues9')
    assert 'my_proc' in dot
    assert '"a"' in dot
    assert '"b0"' in dot
    assert '"b0" -> "a"' in dot
