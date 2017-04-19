import os
import pytest

from desmod.dot import component_to_dot, generate_dot
from desmod.component import Component
from desmod.simulation import SimEnvironment


pytestmark = pytest.mark.usefixtures('cleandir')


@pytest.fixture
def cleandir(tmpdir):
    origin = os.getcwd()
    tmpdir.chdir()
    yield None
    os.chdir(origin)


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


@pytest.mark.parametrize('key', [
    'sim.dot.enable',
    'sim.dot.colorscheme',
    'sim.dot.all.file',
    'sim.dot.hier.file',
    'sim.dot.conn.file',
])
def test_generate_dot(top, key):
    assert key not in top.env.config
    generate_dot(top)
    assert key in top.env.config
    files = os.listdir(os.curdir)
    for key in top.env.config:
        if key.startswith('sim.dot.') and key.endswith('.file'):
            assert top.env.config[key] not in files


@pytest.mark.parametrize('key', [
    'sim.dot.all.file',
    'sim.dot.hier.file',
    'sim.dot.conn.file',
])
def test_generate_dot_file_enables(top, key):
    top.env.config['sim.dot.enable'] = True
    top.env.config[key] = ''
    generate_dot(top)
    assert all(name.endswith('.dot') for name in os.listdir(os.curdir))
