"""Simulation model with batteries included."""
from __future__ import division
from contextlib import contextmanager
import os
import multiprocessing
import random
import shutil
import timeit

import simpy
import six
import yaml

from desmod.config import factorial_config
from desmod.timescale import parse_time, scale_time
from desmod.tracer import TraceManager
from desmod.workspace import Workspace


class SimEnvironment(simpy.Environment):

    def __init__(self, config):
        super(SimEnvironment, self).__init__()
        self.config = config
        self.rand = random.Random()
        if six.PY3:
            self.rand.seed(config['sim.seed'], version=1)
        else:
            self.rand.seed(config['sim.seed'])
        self.timescale = parse_time(self.config['sim.timescale'])
        self.duration = scale_time(parse_time(config['sim.duration']),
                                   self.timescale)


def simulate(config, top_type,
             pre_init_hook=None,
             pre_elab_hook=None,
             pre_sim_hook=None,
             post_sim_hook=None):
    env = SimEnvironment(config)
    result_filename = config['sim.result.file']
    result = {'config': config, 'sim': {}}
    t0 = timeit.default_timer()
    with Workspace(config['sim.workspace'], overwrite=True):
        if pre_init_hook:
            pre_init_hook(env)
        with TraceManager(env) as tracemgr:
            try:
                with _progress_notification(env):
                    top = top_type(parent=None, env=env, tracemgr=tracemgr)
                    if pre_elab_hook:
                        pre_elab_hook(env, top)
                    top.elaborate()
                    if pre_sim_hook:
                        pre_sim_hook(env, top)
                    env.run(until=env.duration)
                    if post_sim_hook:
                        post_sim_hook(env, top)
            except Exception as e:
                result['sim']['exception'] = str(e)
                raise
            else:
                result['sim']['exception'] = None
                now_ts = env.now, env.timescale[1]
                result['sim']['time'] = scale_time(now_ts, (1, 's'))
                top.get_results(result)
            finally:
                result['sim']['runtime'] = timeit.default_timer() - t0
                with open(result_filename, 'w') as result_file:
                    yaml.dump(result, stream=result_file)
    return result


def simulate_factors(base_config, top_type, **kwargs):
    factors = base_config['sim.factors']
    configs = list(factorial_config(base_config, factors, 'sim.special'))
    num_sims = len(configs)
    base_workspace = base_config['sim.workspace']
    for seq, config in enumerate(configs):
        config['sim.seq'] = seq
        config['sim.factors'] = []
        config['sim.workspace'] = os.path.join(base_workspace, str(seq))
    if os.path.isdir(base_workspace):
        shutil.rmtree(base_workspace)
    pool_size = min(num_sims, multiprocessing.cpu_count())
    pool = multiprocessing.Pool(pool_size)
    sim_args = [(config, top_type, kwargs)
                for config in configs]
    promise = pool.map_async(_simulate_trampoline, sim_args)
    if config.get('sim.progress.enable'):
        _consume_progress(base_config, num_sims)
    return promise.get()


def _simulate_trampoline(args):
    config, top_type, kwargs = args
    return simulate(config, top_type, **kwargs)


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


_progress_queue = multiprocessing.Queue()


@contextmanager
def _progress_notification(env):
    if env.config.get('sim.progress.enable'):
        interval = env.duration / 100
        seq = env.config['sim.seq']

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


def _consume_progress(config, num_sims):
    pbar = _get_progressbar(config)
    notifiers = {seq: 0 for seq in range(num_sims)}
    total_progress = 0

    while total_progress < 1:
        seq, progress = _progress_queue.get()
        notifiers[seq] = progress
        total_progress = sum(notifiers.values()) / num_sims
        pbar.update(total_progress)

    pbar.finish()
