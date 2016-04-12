"""Simulation model with batteries included.

"""
try:
    from contextlib import contextmanager, ExitStack
except ImportError:
    from contextlib2 import contextmanager, ExitStack
import random
import timeit

import simpy
import six

from .timescale import parse_time, scale_time


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


class Simulation(object):

    def __init__(self, env, top_cls):
        self.env = env
        self.config = env.config
        self.top_cls = top_cls
        self.top = None
        self.runtime = None
        self._exit_stack = ExitStack()
        self._exit_stack.enter_context(self._capture_runtime())

    def simulate(self, tracemgr):
        with self._exit_stack:
            self.top = self.top_cls(parent=None, env=self.env,
                                    tracemgr=tracemgr)
            self.top.elaborate()

            duration = scale_time(parse_time(self.config['sim.duration']),
                                  self.env.timescale)
            if self.config['sim.progress.enable']:
                self._exit_stack.enter_context(self._progressbar(duration))
            self.top.simulate()
            self.env.run(until=duration)

    @contextmanager
    def _capture_runtime(self):
        t0 = timeit.default_timer()
        try:
            yield None
        finally:
            self.runtime = timeit.default_timer() - t0

    @contextmanager
    def _progressbar(self, duration):
        import progressbar
        pbar = progressbar.ProgressBar(min_value=0,
                                       max_value=duration,
                                       widgets=[progressbar.Percentage(),
                                                progressbar.Bar(),
                                                progressbar.ETA()])
        max_width = self.config.get('sim.progress.max_width')
        if max_width and pbar.term_width > max_width:
            pbar.term_width = max_width

        interval = duration // 100

        def progress():
            while True:
                pbar.update(self.env.now)
                yield self.env.timeout(interval)

        self.env.process(progress())
        try:
            yield pbar
        finally:
            pbar.finish()
