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

from .probemanager import ProbeManager
from .timescale import parse_time, scale_time


class SimEnvironment(simpy.Environment):

    def __init__(self, config, rand, sim):
        super(SimEnvironment, self).__init__()
        self.config = config
        self.rand = rand
        self.sim = sim


class Simulation(object):

    def __init__(self, top_cls, config):
        self.top_cls = top_cls
        self.top = None
        self.config = config
        self.timescale = parse_time(self.config['sim.timescale'])

        rand = random.Random()
        if six.PY3:
            rand.seed(config['sim.seed'], version=1)
        else:
            rand.seed(config['sim.seed'])

        self.env = SimEnvironment(config, rand, self)
        self.runtime = None

    def elaborate(self):
        self.top = self.top_cls(parent=None, env=self.env)
        self.top.elaborate()

    def simulate(self):
        duration = scale_time(parse_time(self.config['sim.duration']),
                              self.timescale)
        with ExitStack() as stack:
            stack.enter_context(self._capture_runtime())
            stack.enter_context(ProbeManager(self.env, self.top.iter_probes()))
            if self.config['sim.progress.enable']:
                stack.enter_context(self._progressbar(duration))
            self.top.simulate()
            self.env.run(simpy.Timeout(self.env, duration))

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
