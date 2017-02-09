import os

import pytest
import simpy

from desmod.component import Component
from desmod.simulation import simulate

pytestmark = pytest.mark.usefixtures('cleandir')


@pytest.fixture
def cleandir(tmpdir):
    origin = os.getcwd()
    tmpdir.chdir()
    yield None
    os.chdir(origin)


@pytest.fixture
def config():
    return {
        'sim.duration': '10 us',
        'sim.log.enable': False,
        'sim.log.file': 'sim.log',
        'sim.log.level': 'INFO',
        'sim.result.file': 'result.yaml',
        'sim.seed': 1234,
        'sim.timescale': '1 us',
        'sim.vcd.dump_file': 'sim.vcd',
        'sim.vcd.enable': False,
        'sim.vcd.gtkw_file': 'sim.gtkw',
        'sim.vcd.start_time': '',
        'sim.vcd.stop_time': '',
        'sim.workspace': 'workspace',
    }


class TopTest(Component):

    base_name = 'top'

    def __init__(self, *args, **kwargs):
        super(TopTest, self).__init__(*args, **kwargs)
        self.container = simpy.Container(self.env)
        self.resource = simpy.Resource(self.env)
        self.a = CompA(self)
        self.b = CompB(self)
        hints = {}
        if self.env.config['sim.log.enable']:
            hints['log'] = {'level': 'INFO'}
        if self.env.config['sim.vcd.enable']:
            hints['vcd'] = {}
        self.auto_probe('container', **hints)
        self.auto_probe('resource', **hints)
        self.add_process(self.loop)

    def connect_children(self):
        self.connect(self.a, 'container')
        self.connect(self.b, 'container')

    def loop(self):
        while True:
            yield self.env.timeout(5)
            with self.resource.request() as req:
                yield req


class CompA(Component):

    base_name = 'a'

    def __init__(self, *args, **kwargs):
        super(CompA, self).__init__(*args, **kwargs)
        self.add_process(self.loop)
        self.add_connections('container')

    def loop(self):
        while True:
            yield self.container.get(3)


class CompB(CompA):

    base_name = 'b'

    def loop(self):
        while True:
            yield self.container.put(1)
            yield self.env.timeout(1)


def test_defaults(config):
    simulate(config, TopTest)
    workspace = config['sim.workspace']
    assert os.path.isdir(workspace)
    assert os.path.exists(os.path.join(workspace, config['sim.result.file']))
    for filename_key in ['sim.log.file',
                         'sim.vcd.dump_file',
                         'sim.vcd.gtkw_file']:
        assert not os.path.exists(os.path.join(workspace,
                                               config[filename_key]))


def test_log(config):
    config['sim.log.enable'] = True
    simulate(config, TopTest)
    log_path = os.path.join(config['sim.workspace'], config['sim.log.file'])
    assert os.path.exists(log_path)
    last_line = open(log_path).readlines()[-1]
    assert last_line == 'INFO    9.000 us: top.container: 1\n'


def test_log_stderr(config, capsys):
    config['sim.log.enable'] = True
    config['sim.log.file'] = ''
    simulate(config, TopTest)
    out, err = capsys.readouterr()
    assert out == ''
    assert err.endswith('INFO    9.000 us: top.container: 1\n')


def test_vcd(config):
    config['sim.vcd.enable'] = True
    simulate(config, TopTest)
    dump_path = os.path.join(config['sim.workspace'],
                             config['sim.vcd.dump_file'])
    assert os.path.exists(dump_path)
    with open(dump_path) as dump:
        vcd_str = dump.read()
        for t in range(1, 11):
            assert '#{}\n'.format(t) in vcd_str


def test_vcd_start(config):
    config['sim.vcd.enable'] = True
    config['sim.vcd.start_time'] = '5 us'
    simulate(config, TopTest)
    dump_path = os.path.join(config['sim.workspace'],
                             config['sim.vcd.dump_file'])
    with open(dump_path) as dump:
        vcd_str = dump.read()
        assert 'dumpon' in vcd_str
        assert '#6' in vcd_str


def test_vcd_stop(config):
    config['sim.vcd.enable'] = True
    config['sim.vcd.stop_time'] = '5 us'
    simulate(config, TopTest)
    dump_path = os.path.join(config['sim.workspace'],
                             config['sim.vcd.dump_file'])
    with open(dump_path) as dump:
        vcd_str = dump.read()
        assert 'dumpoff' in vcd_str
        assert '#6' not in vcd_str


def test_vcd_start_then_stop(config):
    config['sim.vcd.enable'] = True
    config['sim.vcd.start_time'] = '4 us'
    config['sim.vcd.stop_time'] = '6 us'
    simulate(config, TopTest)
    dump_path = os.path.join(config['sim.workspace'],
                             config['sim.vcd.dump_file'])
    with open(dump_path) as dump:
        vcd_str = dump.read()
        assert 'dumpon' in vcd_str
        assert 'dumpoff' in vcd_str
        assert '#1\n' not in vcd_str
        assert '#5' in vcd_str
        assert '#9' not in vcd_str


def test_vcd_stop_then_start(config):
    config['sim.vcd.enable'] = True
    config['sim.vcd.start_time'] = '6 us'
    config['sim.vcd.stop_time'] = '4 us'
    simulate(config, TopTest)
    dump_path = os.path.join(config['sim.workspace'],
                             config['sim.vcd.dump_file'])
    with open(dump_path) as dump:
        vcd_str = dump.read()
        assert 'dumpon' in vcd_str
        assert 'dumpoff' in vcd_str
        assert '#1\n' in vcd_str
        assert '#5' not in vcd_str
        assert '#9' in vcd_str
