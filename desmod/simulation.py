"""Simulation model with batteries included."""

from __future__ import division
from contextlib import closing
from multiprocessing import cpu_count, Process, Queue
from pprint import pprint
from six.moves import filter
from threading import Thread

import json
import os
import random
import shutil
import timeit

import simpy
import six
import yaml

from desmod.config import factorial_config
from desmod.progress import (standalone_progress_manager,
                             get_multi_progress_manager,
                             consume_multi_progress)
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

        #: Simulation timescale ``(magnitude, units)`` tuple. The current
        #: simulation time is ``now * timescale``.
        self.timescale = parse_time(timescale_str)

        duration = config.setdefault('sim.duration', '0 s')

        #: The intended simulation duration, in units of :attr:`timescale`.
        self.duration = scale_time(parse_time(duration), self.timescale)

        #: The simulation runs "until" this event. By default, this is the
        #: configured "sim.duration", but may be overridden by subclasses.
        self.until = self.duration

        #: From 'meta.sim.index', the simulation's index when running multiple
        #: related simulations or `None` for a standalone simulation.
        self.sim_index = config.get('meta.sim.index')

        #: :class:`TraceManager` instance.
        self.tracemgr = TraceManager(self)

    def time(self, t=None, unit='s'):
        """The current simulation time scaled to specified unit.

        :param float t: Time in simulation units. Default is :attr:`now`.
        :param str unit: Unit of time to scale to. Default is 's' (seconds).
        :returns: Simulation time scaled to to `unit`.

        """
        target_scale = parse_time(unit)
        ts_mag, ts_unit = self.timescale
        sim_time = ((self.now if t is None else t) * ts_mag, ts_unit)
        return scale_time(sim_time, target_scale)

    def get_progress(self):
        if isinstance(self.until, SimStopEvent):
            t_stop = self.until.t_stop
        else:
            t_stop = self.until
        return self.sim_index, self.now, t_stop, self.timescale


class SimStopEvent(simpy.Event):
    """Event appropriate for stopping the simulation.

    An instance of this event may be used to override `SimEnvironment.until` to
    dynamically choose when to stop the simulation. The simulation may be
    stopped by calling :meth:`schedule()`. The optional `delay` parameter may
    be used to schedule the simulation to stop at an offset from the current
    simulation time.

    """
    def __init__(self, env):
        super(SimStopEvent, self).__init__(env)
        self.t_stop = None

    def schedule(self, delay=0):
        assert not self.triggered
        assert delay >= 0
        self._ok = True
        self._value = None
        self.env.schedule(self, simpy.events.URGENT, delay)
        self.t_stop = self.env.now + delay


class _Workspace(object):
    """Context manager for workspace directory management."""
    def __init__(self, config):
        self.workspace = config.setdefault('meta.sim.workspace',
                                           config.setdefault('sim.workspace',
                                                             os.curdir))
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


def simulate(config, top_type, env_type=SimEnvironment, reraise=True,
             progress_manager=standalone_progress_manager):
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
    result_file = config.setdefault('sim.result.file')
    config_file = config.setdefault('sim.config.file')
    try:
        with _Workspace(config):
            env = env_type(config)
            with closing(env.tracemgr):
                try:
                    top_type.pre_init(env)
                    env.tracemgr.flush()
                    with progress_manager(env):
                        top = top_type(parent=None, env=env)
                        top.elaborate()
                        env.tracemgr.flush()
                        env.run(until=env.until)
                        env.tracemgr.flush()
                        top.post_simulate()
                        env.tracemgr.flush()
                        top.get_result(result)
                except BaseException as e:
                    env.tracemgr.trace_exception()
                    result['sim.exception'] = repr(e)
                    raise
                else:
                    result['sim.exception'] = None
                finally:
                    env.tracemgr.flush()
                    result['config'] = config
                    result['sim.now'] = env.now
                    result['sim.time'] = env.time()
                    result['sim.runtime'] = timeit.default_timer() - t0
                    _dump_dict(config_file, config)
                    _dump_dict(result_file, result)
    except BaseException as e:
        if reraise:
            raise
        result.setdefault('config', config)
        result.setdefault('sim.runtime', timeit.default_timer() - t0)
        if result.get('sim.exception') is None:
            result['sim.exception'] = repr(e)
    return result


def simulate_factors(base_config, factors, top_type,
                     env_type=SimEnvironment, jobs=None, config_filter=None):
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
    :param function config_filter:
        A function which will be passed a config and returns a bool to filter.
    :returns: Sequence of result dictionaries for each simulation.

    """
    configs = list(factorial_config(base_config, factors, 'meta.sim.special'))
    ws = base_config.setdefault('sim.workspace', os.curdir)
    overwrite = base_config.setdefault('sim.workspace.overwrite', False)

    for index, config in enumerate(configs):
        config['meta.sim.index'] = index
        config['meta.sim.workspace'] = os.path.join(ws, str(index))
    if config_filter is not None:
        configs[:] = filter(config_filter, configs)
    if overwrite and os.path.relpath(ws) != os.curdir and os.path.isdir(ws):
        shutil.rmtree(ws)
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
    if jobs is not None and jobs < 1:
        raise ValueError('Invalid number of jobs: {}'.format(jobs))

    progress_enable = any(config.setdefault('sim.progress.enable', False)
                          for config in configs)

    progress_queue = Queue() if progress_enable else None
    result_queue = Queue()
    config_queue = Queue()

    workspaces = set()
    max_width = 0
    for index, config in enumerate(configs):
        max_width = max(config.setdefault('sim.progress.max_width', 0),
                        max_width)

        workspace = os.path.normpath(
            config.setdefault('meta.sim.workspace',
                              config.setdefault('sim.workspace',
                                                os.curdir)))
        if workspace in workspaces:
            raise ValueError('Duplicate workspace: {}'.format(workspace))
        workspaces.add(workspace)

        config.setdefault('meta.sim.index', index)
        config['sim.progress.enable'] = progress_enable
        config_queue.put(config)

    num_workers = min(len(configs), cpu_count())
    if jobs is not None:
        num_workers = min(num_workers, jobs)

    workers = []
    for i in range(num_workers):
        worker = Process(name='sim-worker-{}'.format(i),
                         target=_simulate_worker,
                         args=(top_type, env_type, False, progress_queue,
                               config_queue, result_queue))
        worker.daemon = True    # Workers die if main process dies.
        worker.start()
        workers.append(worker)
        config_queue.put(None)  # A stop sentinel for each worker.

    if progress_enable:
        progress_thread = Thread(
            target=consume_multi_progress,
            args=(progress_queue, num_workers, len(configs), max_width))
        progress_thread.daemon = True
        progress_thread.start()

    results = [result_queue.get() for _ in configs]

    if progress_enable:
        # Although this is a daemon thread, we still make a token attempt to
        # join with it. This avoids a race with certain testing frameworks
        # (ahem, py.test) that may monkey-patch and close stderr while
        # progress_thread is still using it.
        progress_thread.join(1)

    for worker in workers:
        worker.join(5)

    return sorted(results, key=lambda r: r['config']['meta.sim.index'])


def _simulate_worker(top_type, env_type, reraise, progress_queue, config_queue,
                     result_queue):
    progress_manager = get_multi_progress_manager(progress_queue)
    while True:
        config = config_queue.get()
        if config is None:
            break
        result = simulate(config, top_type, env_type, reraise,
                          progress_manager)
        result_queue.put(result)


def _dump_dict(filename, dump_dict):
    if filename is not None:
        _, ext = os.path.splitext(filename)
        if ext not in ['.yaml', '.yml', '.json', '.py']:
            raise ValueError('Invalid extension: {}'.format(ext))
        with open(filename, 'w') as dump_file:
            if ext in ['.yaml', '.yml']:
                yaml.safe_dump(dump_dict, stream=dump_file)
            elif ext == '.json':
                json.dump(dump_dict, dump_file, sort_keys=True, indent=2)
            else:
                assert ext == '.py'
                pprint(dump_dict, stream=dump_file)
