"""Simulation model with batteries included."""

from __future__ import division
from contextlib import contextmanager
import os
import multiprocessing
import random
import shutil
import sys
import timeit

import simpy
import six
import yaml

from desmod.config import factorial_config
from desmod.timescale import parse_time, scale_time
from desmod.tracer import TraceManager


class SimEnvironment(simpy.Environment):
    """Simulation Environment.

    The :class:`SimEnvironment` class is a :class:`simpy.Environment` subclass
    that adds some useful features:

     - Access to the configuration dictionary (`config`).
     - Access to a seeded pseudo-random number generator (`rand`).
     - Access to the simulation timescale (`timescale`).
     - Access to the simulation duration (`duration`).

    Some models may need to share additional state with all its
    :class:`desmod.component.Component` instances. SimEnvironment may be
    subclassed to add additional members to achieve this sharing.

    :param dict config: A fully-initialized configuration dictionary.

    """
    def __init__(self, config):
        super(SimEnvironment, self).__init__()
        #: The configuration dictionary.
        self.config = config

        #: The pseudo-random number generator; an instance of
        #: :class:`random.Random`.
        self.rand = random.Random()
        if six.PY3:
            self.rand.seed(config['sim.seed'], version=1)
        else:
            self.rand.seed(config['sim.seed'])

        #: Simulation timescale `(magnitude, units)` tuple. The current
        #: simulation time is `env.now * env.timescale`.
        self.timescale = parse_time(self.config['sim.timescale'])

        #: The intended simulation duration, in units of `timescale`.
        self.duration = scale_time(parse_time(config['sim.duration']),
                                   self.timescale)


class _Workspace(object):
    """Context manager for workspace directory management."""
    def __init__(self, config):
        self.workspace = config.get('sim.workspace', os.curdir)
        self.overwrite = config.get('sim.workspace.overwrite', False)
        self.prev_dir = os.getcwd()

    def __enter__(self):
        if os.path.relpath(self.workspace) != os.curdir:
            workspace_exists = os.path.isdir(self.workspace)
            if self.overwrite and workspace_exists:
                shutil.rmtree(self.workspace)
            if self.overwrite or not workspace_exists:
                os.makedirs(self.workspace)
            os.chdir(self.workspace)

    def __exit__(self, *exc):
        os.chdir(self.prev_dir)


def simulate(config, top_type, env_type=SimEnvironment):
    """Initialize, elaborate, and run a simulation.

    :param dict config: Configuration dictionary for the simulation.
    :param top_type: The model's top-level Component subclass.
    :param env_type: :class:`SimEnvironment` subclass.
    :returns:
        Dictionary containing the model-specific results of the simulation.
    """
    env = env_type(config)
    result_filename = config.get('sim.result.file')
    result = {'config': config}
    t0 = timeit.default_timer()
    with _Workspace(config):
        top_type.pre_init(env)
        with TraceManager(env) as tracemgr:
            try:
                with _progress_notification(env):
                    top = top_type(parent=None, env=env, tracemgr=tracemgr)
                    top.elaborate()
                    env.run(until=env.duration)
                    top.post_simulate()
            except Exception as e:
                result['sim.exception'] = repr(e)
                raise
            else:
                result['sim.exception'] = None
                now_ts = env.now, env.timescale[1]
                result['sim.time'] = scale_time(now_ts, (1, 's'))
                top.get_result(result)
            finally:
                result['sim.runtime'] = timeit.default_timer() - t0
                if result_filename is not None:
                    with open(result_filename, 'w') as result_file:
                        yaml.dump(result, stream=result_file)
    return result


def simulate_factors(base_config, top_type,
                     env_type=SimEnvironment, jobs=None):
    """Run multi-factor simulations in separate processes.

    The `'sim.factors'` found in `base_config` are used to compose specialized
    config dictionaries for the simulations.

    The :mod:`python:multiprocessing` module is used run each simulation with a
    separate Python process. This allows multi-factor simulations to run in
    parallel on all available CPU cores.

    :param dict base_config:
        Base configuration dictionary to be specialized. Must contain the
        `'sim.factors'` key/value which specifies one or more configuration
        factors.
    :param top_type: The model's top-level Component subclass.
    :param env_type: :class:`SimEnvironment` subclass.
    :param int jobs: User specified number of concurent processes.
    :returns: Sequence of result dictionaries for each simulation.

    """
    factors = base_config['sim.factors']
    configs = list(factorial_config(base_config, factors, 'sim.special'))
    base_workspace = base_config['sim.workspace']
    for seq, config in enumerate(configs):
        config['sim.factors'] = []
        config['sim.workspace'] = os.path.join(base_workspace, str(seq))
    if os.path.isdir(base_workspace):
        shutil.rmtree(base_workspace)
    return simulate_many(configs, top_type, env_type, jobs)


def simulate_many(configs, top_type, env_type=SimEnvironment, jobs=None):
    """Run multiple experiments in separate processes.

    The :mod:`python:multiprocessing` module is used run each simulation with a
    separate Python process. This allows multi-factor simulations to run in
    parallel on all available CPU cores.

    :param dict configs: list of configuration dictionary for the simulation.
    :param top_type: The model's top-level Component subclass.
    :param env_type: :class:`SimEnvironment` subclass.
    :param int jobs: User specified number of concurent processes.
    :returns: Sequence of result dictionaries for each simulation.

    """
    progress_enable = any(config.get('sim.progress.enable')
                          for config in configs)
    if sys.platform == 'win32' and progress_enable:
        import warnings
        warnings.warn(
            'Disabling sim.progress.enable. Progress bar broken on win32 with '
            'simulate_many().')
        progress_enable = False
    pool_size = min(len(configs), multiprocessing.cpu_count())
    if jobs is not None:
        pool_size = min(pool_size, jobs)
    pool = multiprocessing.Pool(pool_size)
    sim_args = []
    for seq, config in enumerate(configs):
        config['sim.seq'] = seq
        config['sim.progress.enable'] = progress_enable
        sim_args.append((config, top_type, env_type))
    promise = pool.map_async(_simulate_trampoline, sim_args)
    if progress_enable:
        _consume_progress(configs)
    return promise.get()


def _simulate_trampoline(args):
    return simulate(*args)


def _get_progressbar(config):
    import progressbar

    pbar = progressbar.ProgressBar(min_value=0, max_value=1,
                                   widgets=[progressbar.Percentage(),
                                            progressbar.Bar(),
                                            progressbar.ETA()])

    max_width = config.get('sim.progress.max_width')
    if max_width and pbar.term_width > max_width:
        pbar.term_width = max_width

    return pbar


# When using simulate_factors(), each simulation subprocess sends progress
# notifications to the main/parent process via this queue.
# Unfortunately, this mechanism does not work on Windows with spawned
# subprocesses using map_async().
_progress_queue = multiprocessing.Queue()


@contextmanager
def _progress_notification(env):
    if env.config.get('sim.progress.enable'):
        interval = env.duration / 100
        seq = env.config.get('sim.seq')

        if seq is None:
            pbar = _get_progressbar(env.config)

            def progress():
                while True:
                    pbar.update(env.now / env.duration)
                    yield env.timeout(interval)

            env.process(progress())

            try:
                yield None
            finally:
                pbar.finish()
        else:
            def progress():
                while True:
                    _progress_queue.put((seq, env.now / env.duration))
                    yield env.timeout(interval)

            env.process(progress())

            try:
                yield None
            finally:
                _progress_queue.put((seq, 1))
    else:
        yield None


def _consume_progress(configs):
    pbar = _get_progressbar(configs[0])
    notifiers = {config['sim.seq']: 0 for config in configs}
    total_progress = 0

    while total_progress < 1:
        seq, progress = _progress_queue.get()
        notifiers[seq] = progress
        total_progress = sum(notifiers.values()) / len(notifiers)
        pbar.update(total_progress)

    pbar.finish()
