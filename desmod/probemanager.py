try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack

import six

from .tracer import VCDTracer


class ProbeManager(object):

    def __init__(self, env, probes):
        self.stack = ExitStack()
        tracers = [VCDTracer(env)]
        active_tracers = set()
        probe_to_tracers = {}

        for tracer in tracers:
            if tracer.enabled:
                for probe in probes:
                    if tracer.is_probe_enabled(probe):
                        active_tracers.add(tracer)
                        probe_to_tracers.setdefault(probe, []).append(tracer)

        for tracer in active_tracers:
            tracer.open()
            self.stack.enter_context(tracer)

        for probe, tracers in six.iteritems(probe_to_tracers):
            callbacks = [tracer.activate_probe(probe)
                         for tracer in tracers]
            probe.attach(callbacks)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stack.close()
