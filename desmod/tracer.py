from __future__ import print_function
import re
import sys
import traceback

import simpy
from vcd import VCDWriter

from . import probe
from .util import partial_format
from .timescale import parse_time, scale_time
from .queue import Queue


class Tracer(object):

    name = ''

    def __init__(self, env):
        self.env = env
        cfg_scope = 'sim.' + self.name + '.'
        self.enabled = env.config.get(cfg_scope + 'enable', False)
        if self.enabled:
            self.open()
            include_pat = env.config.get(cfg_scope + 'include_pat', ['.*'])
            exclude_pat = env.config.get(cfg_scope + 'exclude_pat', [])
            self._include_re = [re.compile(pat) for pat in include_pat]
            self._exclude_re = [re.compile(pat) for pat in exclude_pat]

    def is_scope_enabled(self, scope):
        return (self.enabled and
                any(r.match(scope) for r in self._include_re) and
                not any(r.match(scope) for r in self._exclude_re))

    def open(self):
        raise NotImplementedError()

    def close(self):
        if self.enabled:
            self._close()

    def _close(self):
        raise NotImplementedError()

    def activate_probe(self, scope, target, **hints):
        raise NotImplementedError()

    def activate_trace(self, scope, **hints):
        raise NotImplementedError()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class LogTracer(Tracer):

    name = 'log'
    default_format = '{level:7} {ts:.3f} {ts_unit}: {scope}:'

    levels = {
        'ERROR': 1,
        'WARNING': 2,
        'INFO': 3,
        'PROBE': 4,
        'DEBUG': 5,
    }

    def open(self):
        log_filename = self.env.config.get('sim.log.file')
        buffering = self.env.config.get('sim.log.buffering', -1)
        self.max_level = self.levels[self.env.config.get('sim.log.level',
                                                         'INFO')]
        self.format_str = self.env.config.get('sim.log.format',
                                              self.default_format)
        ts_n, ts_unit = self.env.timescale
        if ts_n == 1:
            self.ts_unit = ts_unit
        else:
            self.ts_unit = '({}{})'.format(ts_n, ts_unit)

        if log_filename:
            self.file = open(log_filename, 'w', buffering)
            self.should_close = True
        else:
            self.file = sys.stderr
            self.should_close = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and self.enabled:
            tb_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
            print(self.format_str.format(level='ERROR',
                                         ts=self.env.now,
                                         ts_unit=self.ts_unit,
                                         scope='Exception'),
                  tb_lines[-1], '\n', *tb_lines, file=self.file)
        self.close()

    def _close(self):
        if self.should_close:
            self.file.close()

    def is_scope_enabled(self, scope, level=None):
        return ((level is None or self.levels[level] <= self.max_level) and
                super(LogTracer, self).is_scope_enabled(scope))

    def activate_probe(self, scope, target, **hints):
        level = hints.get('level', 'PROBE')
        if not self.is_scope_enabled(scope, level):
            return None
        format_str = partial_format(self.format_str,
                                    level=level,
                                    ts_unit=self.ts_unit,
                                    scope=scope)

        def probe_callback(value):
            print(format_str.format(ts=self.env.now), value, file=self.file)

        return probe_callback

    def activate_trace(self, scope, **hints):
        level = hints.get('level', 'DEBUG')
        if not self.is_scope_enabled(scope, level):
            return None
        format_str = partial_format(self.format_str,
                                    level=level,
                                    ts_unit=self.ts_unit,
                                    scope=scope)

        def trace_callback(*value):
            print(format_str.format(ts=self.env.now), *value, file=self.file)

        return trace_callback


class VCDTracer(Tracer):

    name = 'vcd'

    def open(self):
        dump_filename = self.env.config['sim.vcd.dump_file']
        if 'sim.vcd.timescale' in self.env.config:
            vcd_timescale = parse_time(self.env.config['sim.vcd.timescale'])
        else:
            vcd_timescale = self.env.timescale
        self.scale_factor = scale_time(self.env.timescale, vcd_timescale)
        check_values = self.env.config.get('sim.vcd.check_values', True)
        self.dump_file = open(dump_filename, 'w')
        self.vcd = VCDWriter(self.dump_file,
                             timescale=vcd_timescale,
                             check_values=check_values)
        if self.env.config.get('sim.gtkw.live'):
            from vcd.gtkw import spawn_gtkwave_interactive
            save_filename = self.env.config['sim.gtkw.file']
            quiet = self.env.config.get('sim.gtkw.quiet', True)
            spawn_gtkwave_interactive(dump_filename, save_filename,
                                      quiet=quiet)

    def vcd_now(self):
        return self.env.now * self.scale_factor

    def _close(self):
        self.vcd.close(self.vcd_now())
        self.dump_file.close()

    def activate_probe(self, scope, target, **hints):
        assert self.enabled
        var_type = hints.get('var_type')
        if var_type is None:
            if isinstance(target, simpy.Container):
                if isinstance(target.level, float):
                    var_type = 'real'
                else:
                    var_type = 'integer'
            elif isinstance(target, (simpy.Resource, simpy.Store, Queue)):
                var_type = 'integer'
            else:
                raise ValueError(
                    'Could not infer VCD var_type for {}'.format(scope))

        kwargs = {k: hints[k]
                  for k in ['size', 'init', 'ident']
                  if k in hints}

        if 'init' not in kwargs:
            if isinstance(target, simpy.Container):
                kwargs['init'] = target.level
            elif isinstance(target, simpy.Resource):
                kwargs['init'] = len(target.users) if target.users else 'z'
            elif isinstance(target, (simpy.Store, Queue)):
                kwargs['init'] = len(target.items)

        parent_scope, name = scope.rsplit('.', 1)
        var = self.vcd.register_var(parent_scope, name, var_type, **kwargs)

        def probe_callback(value):
            self.vcd.change(var, self.vcd_now(), value)

        return probe_callback

    def activate_trace(self, scope, **hints):
        assert self.enabled
        var_type = hints['var_type']
        kwargs = {k: hints[k]
                  for k in ['size', 'init', 'ident']
                  if k in hints}

        parent_scope, name = scope.rsplit('.', 1)
        var = self.vcd.register_var(parent_scope, name, var_type, **kwargs)

        if isinstance(var.size, tuple):
            def trace_callback(*value):
                self.vcd.change(var, self.vcd_now(), value)
        else:
            def trace_callback(value):
                self.vcd.change(var, self.vcd_now(), value)

        return trace_callback


class TraceManager(object):

    def __init__(self, env):
        self.tracers = []
        try:
            for tracer_type in [LogTracer, VCDTracer]:
                self.tracers.append(tracer_type(env))
        except:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for tracer in self.tracers:
            tracer.__exit__(*exc)

    def close(self):
        for tracer in self.tracers:
            tracer.close()

    def auto_probe(self, scope, target, **hints):
        callbacks = []
        for tracer in self.tracers:
            if tracer.name in hints and tracer.is_scope_enabled(scope):
                callback = tracer.activate_probe(scope, target,
                                                 **hints[tracer.name])
                if callback:
                    callbacks.append(callback)
        if callbacks:
            probe.attach(scope, target, callbacks, **hints)

    def get_trace_function(self, scope, **hints):
        callbacks = []
        for tracer in self.tracers:
            if tracer.name in hints and tracer.is_scope_enabled(scope):
                callback = tracer.activate_trace(scope, **hints[tracer.name])
                if callback:
                    callbacks.append(callback)

        def trace_function(*value):
            for callback in callbacks:
                callback(*value)

        return trace_function
