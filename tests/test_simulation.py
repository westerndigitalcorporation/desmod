import os
import pytest

from desmod.component import Component
from desmod.simulation import simulate, SimEnvironment


@pytest.fixture
def config():
    return {
        'sim.workspace': 'workspace',
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
        if self.env.config.get('test.fail_simulate'):
            raise Exception('fail_simulate')
        yield self.env.timeout(1)

    def post_sim_hook(self):
        if self.env.config.get('test.fail_post_simulate'):
            raise Exception('fail_post_simulate')

    def get_result_hook(self, result):
        if self.env.config.get('test.fail_get_result'):
            raise Exception('fail_get_result')


def test_workspace_env_init(tmpdir, config):
    class TestEnvironment(SimEnvironment):
        def __init__(self, config):
            super(TestEnvironment, self).__init__(config)
            assert os.path.split(os.getcwd())[-1] == config['sim.workspace']

    with tmpdir.as_cwd():
        workspace = config['sim.workspace']
        assert not os.path.exists(workspace)
        simulate(config, TopTest, TestEnvironment)
        assert os.path.exists(workspace)


def test_sim_time(tmpdir, config):
    config['sim.timescale'] = '10 ms'
    config['sim.duration'] = '995 ms'
    with tmpdir.as_cwd():
        result = simulate(config, TopTest)
        assert result['sim.time'] == 0.995
        assert result['sim.now'] == 99.5
