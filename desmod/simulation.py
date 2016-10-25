"""Simulation model with batteries included."""

from __future__ import division
from contextlib import contextmanager, closing
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
        seed = config.setdefault('sim.seed', None)
        if six.PY3:
            self.rand.seed(seed, version=1)
        else:
            self.rand.seed(seed)

        timescale_str = self.config.setdefault('sim.timescale', '1 s')

        #: Simulation timescale `(magnitude, units)` tuple. The current
        #: simulation time is `env.now * env.timescale`.
        self.timescale = parse_time(timescale_str)

        duration = config.setdefault('sim.duration', '0 s')

        #: The intended simulation duration, in units of `timescale`.
        self.duration = scale_time(parse_time(duration), self.timescale)

        #: TraceManager instance.
        self.tracemgr = TraceManager(self)

    def time(self, unit='s'):
        """The current simulation time scaled to specified unit.

        :param str unit: Unit of time to scale to. Default is 's' (seconds).
        :returns: Current simulation time scaled to to `unit`.

        """
        ts_mag, ts_unit = self.timescale
        return scale_time((self.now * ts_mag, ts_unit), (1, unit))


class _Workspace(object):
    """Context manager for workspace directory management."""
    def __init__(self, config):
        self.workspace = config.setdefault('sim.workspace', os.curdir)
        self.overwrite = config.setdefault('sim.workspace.overwrite', False)
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


def simulate(config, top_type, env_type=SimEnvironment, reraise=True):
    """Initialize, elaborate, and run a simulation.

     All exceptions are caught by `simulate()` so they can be logged and
     captured in the result file. By default, any unhandled exception caught by
     `simulate()` will be re-raised. Setting `reraise` to False prevents
     exceptions from propagating to the caller. Instead, the returned result
     dict will indicate if an exception occurred via the 'sim.exception' item.

    :param dict config: Configuration dictionary for the simulation.
    :param top_type: The model's top-level Component subclass.
    :param env_type: :class:`SimEnvironment` subclass.
    :param bool reraise: Should unhandled exceptions propogate to the caller.
    :returns:
        Dictionary containing the model-specific results of the simulation.
    """
    t0 = timeit.default_timer()
    result = {}
    try:
        with _Workspace(config):
            env = env_type(config)
            with closing(env.tracemgr):
                try:
                    top_type.pre_init(env)
                    with _progress_notification(env):
                        top = top_type(parent=None, env=env)
                        top.elaborate()
                        env.run(until=env.duration)
                        top.post_simulate()
                        top.get_result(result)
                except BaseException as e:
                    env.tracemgr.trace_exception()
                    result['sim.exception'] = repr(e)
                    raise
                else:
                    result['sim.exception'] = None
                finally:
                    result['config'] = config
                    result['sim.now'] = env.now
                    result['sim.time'] = env.time()
                    result['sim.runtime'] = timeit.default_timer() - t0
                    _dump_result(config.setdefault('sim.result.file'), result)
    except BaseException as e:
        if reraise:
            raise
        result.setdefault('config', config)
        result.setdefault('sim.runtime', timeit.default_timer() - t0)
        if result.get('sim.exception') is None:
            result['sim.exception'] = repr(e)
    return result


def simulate_factors(base_config, factors, top_type,
                     env_type=SimEnvironment, jobs=None):
    """Run multi-factor simulations in separate processes.

    The `factors` are used to compose specialized config dictionaries for the
    simulations.

    The :mod:`python:multiprocessing` module is used run each simulation with a
    separate Python process. This allows multi-factor simulations to run in
    parallel on all available CPU cores.

    :param dict base_config: Base configuration dictionary to be specialized.
    :param list factors: List of factors.
    :param top_type: The model's top-level Component subclass.
    :param env_type: :class:`SimEnvironment` subclass.
    :param int jobs: User specified number of concurent processes.
    :returns: Sequence of result dictionaries for each simulation.

    """
    configs = list(factorial_config(base_config, factors, 'sim.special'))
    base_workspace = base_config.setdefault('sim.workspace', os.curdir)
    overwrite = base_config.setdefault('sim.workspace.overwrite', False)
    for seq, config in enumerate(configs):
        config['sim.workspace'] = os.path.join(base_workspace, str(seq))
    if (overwrite and
            os.path.relpath(base_workspace) != os.curdir and
            os.path.isdir(base_workspace)):
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
    progress_enable = any(config.setdefault('sim.progress.enable', False)
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
        sim_args.append((config, top_type, env_type, False))
    promise = pool.map_async(_simulate_trampoline, sim_args)
    if progress_enable:
        _consume_progress(configs)
    return promise.get()


def _simulate_trampoline(args):
    return simulate(*args)


def _dump_result(filename, result):
    if filename is not None:
        with open(filename, 'w') as result_file:
            yaml.safe_dump(result, stream=result_file)


def _get_progressbar(config):
    import progressbar

    pbar = progressbar.ProgressBar(min_value=0, max_value=1,
                                   widgets=[progressbar.Percentage(),
                                            progressbar.Bar(),
                                            progressbar.ETA()])

    max_width = config.setdefault('sim.progress.max_width')
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
    if env.config.setdefault('sim.progress.enable', False):
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
