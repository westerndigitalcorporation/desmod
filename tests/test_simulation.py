import os
import pytest

from desmod.component import Component
from desmod.simulation import simulate, simulate_factors, SimEnvironment


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
        'sim.result.file': 'result.yaml',
        'sim.workspace': 'workspace',
        'sim.workspace.overwrite': False,
        'sim.timescale': '1 us',
        'sim.seed': 1234,
        'sim.duration': '1 us',
        'test.ensure_workspace': False,
        'test.fail_pre_init': False,
        'test.fail_init': False,
        'test.fail_simulate': False,
        'test.fail_post_simulate': False,
        'test.fail_get_result': False,
    }


class TopTest(Component):

    @classmethod
    def pre_init(cls, env):
        if env.config.get('test.fail_pre_init'):
            raise Exception('fail_pre_init')
        if env.config.get('test.ensure_workspace'):
            cwd = os.path.split(os.getcwd())[-1]
            assert cwd == env.config['sim.workspace']

    def __init__(self, *args, **kwargs):
        super(TopTest, self).__init__(*args, **kwargs)
        if self.env.config.get('test.fail_init'):
            raise Exception('fail_init')
        self.add_process(self.test_proc)

    def test_proc(self):
        yield self.env.timeout(0.5)
        if self.env.config.get('test.fail_simulate'):
            assert False, 'fail_simulate'
        yield self.env.timeout(0.5)

    def post_sim_hook(self):
        if self.env.config.get('test.fail_post_simulate'):
            raise Exception('fail_post_simulate')

    def get_result_hook(self, result):
        if self.env.config.get('test.fail_get_result'):
            raise Exception('fail_get_result')


def test_pre_init_failure(config):
    config['test.fail_pre_init'] = True
    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'] == repr(Exception('fail_pre_init'))
    assert result['sim.now'] == 0
    assert result['sim.time'] == 0
    assert result['sim.runtime'] > 0
    assert result['config']['test.fail_pre_init']
    assert os.path.exists(os.path.join(config['sim.workspace'],
                                       config['sim.result.file']))


def test_init_failure(config):
    config['test.fail_init'] = True
    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'] == repr(Exception('fail_init'))
    assert result['sim.now'] == 0
    assert result['sim.time'] == 0
    assert result['sim.runtime'] > 0
    assert result['config']['test.fail_init']
    assert os.path.exists(os.path.join(config['sim.workspace'],
                                       config['sim.result.file']))


def test_simulate_fail(config):
    config['test.fail_simulate'] = True
    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'].startswith('AssertionError')
    assert result['sim.now'] == 0.5
    assert result['sim.time'] == 0.5e-6
    assert result['sim.runtime'] > 0
    assert result['config']['test.fail_simulate']
    assert os.path.exists(os.path.join(config['sim.workspace'],
                                       config['sim.result.file']))


def test_post_simulate_fail(config):
    config['test.fail_post_simulate'] = True
    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'] == repr(Exception('fail_post_simulate'))
    assert result['sim.now'] == 1
    assert result['sim.time'] == 1e-6
    assert result['sim.runtime'] > 0
    assert result['config']['test.fail_post_simulate']
    assert os.path.exists(os.path.join(config['sim.workspace'],
                                       config['sim.result.file']))


def test_get_result_fail(config):
    config['test.fail_get_result'] = True
    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'] == repr(Exception('fail_get_result'))
    assert result['sim.now'] == 1
    assert result['sim.time'] == 1e-6
    assert result['sim.runtime'] > 0
    assert result['config']['test.fail_get_result']
    assert os.path.exists(os.path.join(config['sim.workspace'],
                                       config['sim.result.file']))


def test_simulate_reraise(config):
    config['test.fail_simulate'] = True
    with pytest.raises(AssertionError):
        simulate(config, TopTest, reraise=True)


def test_no_result_file(config):
    config.pop('sim.result.file')
    result = simulate(config, TopTest)
    assert result['sim.exception'] is None
    assert not os.listdir(config['sim.workspace'])


def test_simulate_factors(config):
    factors = [(['sim.seed'], [[1], [2], [3]])]
    results = simulate_factors(config, factors, TopTest)
    assert len(results) == 3
    for result in results:
        assert result['sim.exception'] is None
        assert os.path.exists(
            os.path.join(result['config']['sim.workspace'],
                         result['config']['sim.result.file']))


def test_simulate_factors_no_overwrite(config):
    config['sim.workspace.overwrite'] = False
    factors = [(['sim.seed'], [[1], [2], [3]])]
    results = simulate_factors(config, factors, TopTest)
    assert os.path.isdir(config['sim.workspace'])
    assert len(results) == 3
    for result in results:
        assert result['sim.exception'] is None
        assert os.path.exists(
            os.path.join(result['config']['sim.workspace'],
                         result['config']['sim.result.file']))

    with open(os.path.join(config['sim.workspace'], 'cookie.txt'), 'w') as f:
        f.write('hi')

    factors = [(['sim.seed'], [[1], [2], [3], [4]])]
    results = simulate_factors(config, factors, TopTest)
    assert len(results) == 4
    assert os.path.isdir(config['sim.workspace'])
    for result in results:
        assert result['sim.exception'] is None
        assert os.path.exists(
            os.path.join(result['config']['sim.workspace'],
                         result['config']['sim.result.file']))

    with open(os.path.join(config['sim.workspace'], 'cookie.txt')) as f:
        assert f.read() == 'hi'


def test_simulate_factors_overwrite(config):
    config['sim.workspace.overwrite'] = True
    factors = [(['sim.seed'], [[1], [2], [3]])]
    results = simulate_factors(config, factors, TopTest)
    assert os.path.isdir(config['sim.workspace'])
    assert len(results) == 3
    for result in results:
        assert result['sim.exception'] is None
        assert os.path.exists(
            os.path.join(result['config']['sim.workspace'],
                         result['config']['sim.result.file']))

    with open(os.path.join(config['sim.workspace'], 'cookie.txt'), 'w') as f:
        f.write('hi')

    factors = [(['sim.seed'], [[1], [2]])]
    results = simulate_factors(config, factors, TopTest)
    assert len(results) == 2
    assert os.path.isdir(config['sim.workspace'])
    for result in results:
        assert result['sim.exception'] is None
        assert os.path.exists(
            os.path.join(result['config']['sim.workspace'],
                         result['config']['sim.result.file']))

    assert not os.path.exists(os.path.join(config['sim.workspace'],
                                           'cookie.txt'))
    assert set(os.listdir(config['sim.workspace'])) == set(['0', '1'])


def test_progress_enabled(config):
    config['sim.progress.enable'] = True
    result = simulate(config, TopTest)
    assert result['sim.exception'] is None
    assert result['sim.now'] == 1
    assert result['sim.time'] == 1e-6
    assert result['sim.runtime'] > 0
    assert os.path.exists(os.path.join(config['sim.workspace'],
                                       config['sim.result.file']))


def test_many_progress_enabled(config):
    config['sim.progress.enable'] = True
    factors = [(['sim.seed'], [[1], [2], [3]])]
    results = simulate_factors(config, factors, TopTest)
    for result in results:
        assert result['sim.exception'] is None
        assert result['sim.now'] == 1
        assert result['sim.time'] == 1e-6
        assert result['sim.runtime'] > 0
        assert os.path.exists(
            os.path.join(result['config']['sim.workspace'],
                         result['config']['sim.result.file']))


def test_workspace_env_init(config):
    class TestEnvironment(SimEnvironment):
        def __init__(self, config):
            super(TestEnvironment, self).__init__(config)
            assert os.path.split(os.getcwd())[-1] == config['sim.workspace']

    workspace = config['sim.workspace']
    assert not os.path.exists(workspace)
    simulate(config, TopTest, TestEnvironment)
    assert os.path.exists(workspace)


def test_workspace_no_overwrite(config):
    workspace = config['sim.workspace']

    config['sim.workspace.overwrite'] = True
    config['sim.result.file'] = 'first-result.yaml'
    assert not os.path.exists(workspace)
    simulate(config, TopTest)
    assert os.path.exists(os.path.join(workspace, 'first-result.yaml'))

    config['sim.workspace.overwrite'] = False
    config['sim.result.file'] = 'second-result.yaml'
    simulate(config, TopTest)
    assert os.path.exists(os.path.join(workspace, 'first-result.yaml'))
    assert os.path.exists(os.path.join(workspace, 'second-result.yaml'))

    config['sim.workspace.overwrite'] = True
    config['sim.result.file'] = 'third-result.yaml'
    simulate(config, TopTest)
    assert not os.path.exists(os.path.join(workspace, 'first-result.yaml'))
    assert not os.path.exists(os.path.join(workspace, 'second-result.yaml'))
    assert os.path.exists(os.path.join(workspace, 'third-result.yaml'))


def test_workspace_is_curdir(config):
    config['sim.workspace'] = '.'
    config['sim.workspace.overwrite'] = True
    config['sim.result.file'] = 'first-result.yaml'
    simulate(config, TopTest)
    assert os.path.exists('first-result.yaml')

    config['sim.workspace.overwrite'] = True
    config['sim.result.file'] = 'second-result.yaml'
    simulate(config, TopTest)
    # '.' is not supposed to be overwritten
    assert os.path.exists('first-result.yaml')
    assert os.path.exists('second-result.yaml')


def test_sim_time(config):
    config['sim.timescale'] = '10 ms'
    config['sim.duration'] = '995 ms'
    result = simulate(config, TopTest)
    assert result['sim.time'] == 0.995
    assert result['sim.now'] == 99.5
