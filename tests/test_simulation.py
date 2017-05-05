import json
import os
import pytest

import yaml

from desmod.component import Component
from desmod.simulation import (simulate, simulate_factors, simulate_many,
                               SimEnvironment, SimStopEvent)
import desmod.progress


pytestmark = pytest.mark.usefixtures('cleandir')


@pytest.fixture
def cleandir(tmpdir):
    origin = os.getcwd()
    tmpdir.chdir()
    yield None
    os.chdir(origin)


@pytest.fixture
def no_progressbar(monkeypatch):
    monkeypatch.setattr(desmod.progress, 'progressbar', None)


@pytest.fixture
def no_colorama(monkeypatch):
    monkeypatch.setattr(desmod.progress, 'colorama', None)


@pytest.fixture
def config():
    return {
        'sim.config.file': 'config.yaml',
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
        'test.until_delay': None,
    }


class TopTest(Component):

    @classmethod
    def pre_init(cls, env):
        if env.config.get('test.fail_pre_init'):
            raise Exception('fail_pre_init')

    def __init__(self, *args, **kwargs):
        super(TopTest, self).__init__(*args, **kwargs)
        if self.env.config.get('test.fail_init'):
            raise Exception('fail_init')
        self.add_process(self.test_proc)

    def test_proc(self):
        yield self.env.timeout(0.5)
        if self.env.config.get('test.fail_simulate'):
            assert False, 'fail_simulate'
        until_delay = self.env.config.get('test.until_delay')
        if until_delay is not None:
            self.env.until.schedule(until_delay)
        yield self.env.timeout(0.5)

    def post_sim_hook(self):
        if self.env.config.get('test.fail_post_simulate'):
            raise Exception('fail_post_simulate')

    def get_result_hook(self, result):
        if self.env.config.get('test.fail_get_result'):
            raise Exception('fail_get_result')
        result['time_100ps'] = self.env.time(unit='100 ps')


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
    for file_key in ['sim.result.file', 'sim.config.file']:
        assert os.path.exists(os.path.join(config['sim.workspace'],
                                           config[file_key]))


def test_simulate_fail(config):
    config['test.fail_simulate'] = True
    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'].startswith('AssertionError')
    assert result['sim.now'] == 0.5
    assert result['sim.time'] == 0.5e-6
    assert result['sim.runtime'] > 0
    assert result['config']['test.fail_simulate']
    for file_key in ['sim.result.file', 'sim.config.file']:
        assert os.path.exists(os.path.join(config['sim.workspace'],
                                           config[file_key]))


def test_post_simulate_fail(config):
    config['test.fail_post_simulate'] = True
    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'] == repr(Exception('fail_post_simulate'))
    assert result['sim.now'] == 1
    assert result['sim.time'] == 1e-6
    assert result['sim.runtime'] > 0
    assert result['config']['test.fail_post_simulate']
    for file_key in ['sim.result.file', 'sim.config.file']:
        assert os.path.exists(os.path.join(config['sim.workspace'],
                                           config[file_key]))


def test_get_result_fail(config):
    config['test.fail_get_result'] = True
    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'] == repr(Exception('fail_get_result'))
    assert result['sim.now'] == 1
    assert result['sim.time'] == 1e-6
    assert result['sim.runtime'] > 0
    assert result['config']['test.fail_get_result']
    for file_key in ['sim.result.file', 'sim.config.file']:
        assert os.path.exists(os.path.join(config['sim.workspace'],
                                           config[file_key]))


def test_simulate_reraise(config):
    config['test.fail_simulate'] = True
    with pytest.raises(AssertionError):
        simulate(config, TopTest, reraise=True)


def test_no_result_file(config):
    config.pop('sim.result.file')
    config.pop('sim.config.file')
    result = simulate(config, TopTest)
    assert result['sim.exception'] is None
    assert not os.listdir(config['sim.workspace'])


def test_simulate_with_progress(config, capsys):
    config['sim.progress.enable'] = True
    config['sim.duration'] = '10 us'
    simulate(config, TopTest)
    _, err = capsys.readouterr()
    assert err.endswith('(100%)\n')


@pytest.mark.parametrize('max_width', [0, 1])
def test_simulate_with_progress_tty(config, capsys, max_width):
    config['sim.progress.enable'] = True
    config['sim.progress.max_width'] = max_width
    config['sim.duration'] = '10 us'
    with capsys.disabled():
        simulate(config, TopTest)


def test_simulate_progress_non_one_timescale(config):
    config['sim.progress.enable'] = True
    config['sim.timescale'] = '100 ns'
    config['sim.duration'] = '10 us'
    simulate(config, TopTest)


def test_simulate_factors(config):
    factors = [(['sim.seed'], [[1], [2], [3]])]
    results = simulate_factors(config, factors, TopTest)
    assert len(results) == 3
    for result in results:
        assert result['sim.exception'] is None
        assert os.path.exists(
            os.path.join(result['config']['meta.sim.workspace'],
                         result['config']['sim.result.file']))


def test_simulate_factors_only_factor(config):
    FACTOR_NUM = 2

    def single_factor_filter_fn(cfg):
        return cfg['meta.sim.index'] == FACTOR_NUM

    factors = [(['sim.seed'], [[1], [2], [3]])]
    results = simulate_factors(
        config, factors, TopTest, config_filter=single_factor_filter_fn)
    assert len(results) == 1
    for result in results:
        assert result['sim.exception'] is None
        assert result['config']['meta.sim.workspace'] == os.path.join(
            config['sim.workspace'], str(FACTOR_NUM))
        assert os.path.exists(
            os.path.join(result['config']['meta.sim.workspace'],
                         result['config']['sim.result.file']))


def test_simulate_factors_progress(config, capfd):
    config['sim.progress.enable'] = True
    config['sim.duration'] = '10 us'
    factors = [(['sim.seed'], [[1], [2], [3]])]
    results = simulate_factors(config, factors, TopTest)
    assert len(results) == 3
    for result in results:
        assert result['sim.exception'] is None
        assert os.path.exists(
            os.path.join(result['config']['meta.sim.workspace'],
                         result['config']['sim.result.file']))
    out, err = capfd.readouterr()
    assert out == ''
    assert '3 of 3 simulations' in err


def test_simulate_factors_progress_tty(config, capsys):
    config['sim.progress.enable'] = True
    config['sim.duration'] = '10 us'
    factors = [(['sim.seed'], [[1], [2], [3]])]
    with capsys.disabled():
        results = simulate_factors(config, factors, TopTest)
    assert len(results) == 3
    for result in results:
        assert result['sim.exception'] is None
        assert os.path.exists(
            os.path.join(result['config']['meta.sim.workspace'],
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
            os.path.join(result['config']['meta.sim.workspace'],
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
            os.path.join(result['config']['meta.sim.workspace'],
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
            os.path.join(result['config']['meta.sim.workspace'],
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
            os.path.join(result['config']['meta.sim.workspace'],
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


@pytest.mark.parametrize('max_width', [0, 1])
def test_many_progress_enabled(config, max_width):
    config['sim.progress.enable'] = True
    config['sim.progress.max_width'] = max_width
    factors = [(['sim.seed'], [[1], [2], [3]])]
    results = simulate_factors(config, factors, TopTest)
    for result in results:
        assert result['sim.exception'] is None
        assert result['sim.now'] == 1
        assert result['sim.time'] == 1e-6
        assert result['sim.runtime'] > 0
        assert os.path.exists(
            os.path.join(result['config']['meta.sim.workspace'],
                         result['config']['sim.result.file']))


def test_many_progress_no_pbar(config, capsys, no_progressbar):
    config['sim.progress.enable'] = True
    config['sim.duration'] = '10 us'
    factors = [(['sim.seed'], [[1], [2], [3]])]
    with capsys.disabled():
        simulate_factors(config, factors, TopTest)


def test_many_progress_no_colorama(config, capsys, no_colorama):
    config['sim.progress.enable'] = True
    factors = [(['sim.seed'], [[1], [2], [3]])]
    with capsys.disabled():
        simulate_factors(config, factors, TopTest)


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


def test_many_with_duplicate_workspace(config):
    configs = [config.copy() for _ in range(2)]
    configs[0]['sim.workspace'] = os.path.join('tmp', os.pardir, 'workspace')
    configs[1]['sim.workspace'] = 'workspace'
    with pytest.raises(ValueError):
        simulate_many(configs, TopTest)


def test_many_user_jobs(config):
    simulate_many([config], TopTest, jobs=1)


def test_many_invalid_jobs(config):
    with pytest.raises(ValueError):
        simulate_many([config], TopTest, jobs=0)


def test_sim_time(config):
    config['sim.timescale'] = '10 ms'
    config['sim.duration'] = '995 ms'
    result = simulate(config, TopTest)
    assert result['sim.time'] == 0.995
    assert result['sim.now'] == 99.5
    assert result['time_100ps'] == 9950000000


def test_sim_time_non_default_t(config):
    config['sim.timescale'] = '1 ms'
    env = SimEnvironment(config)
    assert env.time(1000, 's') == 1
    assert env.time(1, 'ms') == 1
    assert env.time(t=500) == 0.5


@pytest.mark.parametrize('progress_enable', [True, False])
def test_sim_until(config, progress_enable):
    class TestEnvironment(SimEnvironment):
        def __init__(self, config):
            super(TestEnvironment, self).__init__(config)
            self.until = SimStopEvent(self)

    config['sim.progress.enable'] = progress_enable
    config['test.until_delay'] = 0
    result = simulate(config, TopTest, TestEnvironment)
    assert result['sim.now'] == 0.50

    config['test.until_delay'] = 0.25
    result = simulate(config, TopTest, TestEnvironment)
    assert result['sim.now'] == 0.75


def test_sim_json_result(config):
    config['sim.result.file'] = 'result.json'
    result = simulate(config, TopTest)
    workspace = config['sim.workspace']
    with open(os.path.join(workspace, config['sim.result.file'])) as f:
        assert json.load(f) == result


@pytest.mark.parametrize('ext, parser', [
    ('yaml', yaml.load),
    ('yml', yaml.load),
    ('json', json.load),
    ('py', lambda f: eval(f.read())),
])
def test_sim_result_format(config, ext, parser):
    config['sim.result.file'] = 'result.' + ext
    config['sim.config.file'] = 'config.' + ext
    result = simulate(config, TopTest)
    workspace = config['sim.workspace']
    with open(os.path.join(workspace, config['sim.result.file'])) as f:
        assert parser(f) == result
    with open(os.path.join(workspace, config['sim.config.file'])) as f:
        assert parser(f) == config


def test_sim_invalid_result_format(config):
    config['sim.result.file'] = 'result.bogus'
    with pytest.raises(ValueError):
        simulate(config, TopTest)

    result = simulate(config, TopTest, reraise=False)
    assert result['sim.exception'] is not None
