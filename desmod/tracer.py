from typing import TYPE_CHECKING, Any, Callable, Generator, List, Optional, Union
import os
import re
import sqlite3
import sys
import traceback

from vcd import VCDWriter
import simpy

from .pool import Pool
from .probe import ProbeCallback, ProbeTarget
from .probe import attach as probe_attach
from .queue import Queue
from .timescale import parse_time, scale_time
from .util import partial_format

if TYPE_CHECKING:
    from .simulation import SimEnvironment

TraceCallback = Callable[..., None]


class Tracer:

    name: str = ''

    def __init__(self, env: 'SimEnvironment'):
        self.env = env
        cfg_scope = f'sim.{self.name}'
        self.enabled: bool = env.config.setdefault(f'{cfg_scope}.enable', False)
        self.persist: bool = env.config.setdefault(f'{cfg_scope}.persist', True)
        if self.enabled:
            self.open()
            include_pat: List[str] = env.config.setdefault(
                f'{cfg_scope}.include_pat', ['.*']
            )
            exclude_pat: List[str] = env.config.setdefault(
                f'{cfg_scope}.exclude_pat', []
            )
            self._include_re = [re.compile(pat) for pat in include_pat]
            self._exclude_re = [re.compile(pat) for pat in exclude_pat]

    def is_scope_enabled(self, scope: str) -> bool:
        return (
            self.enabled
            and any(r.match(scope) for r in self._include_re)
            and not any(r.match(scope) for r in self._exclude_re)
        )

    def open(self) -> None:
        raise NotImplementedError()  # pragma: no cover

    def close(self) -> None:
        if self.enabled:
            self._close()

    def _close(self) -> None:
        raise NotImplementedError()  # pragma: no cover

    def remove_files(self) -> None:
        raise NotImplementedError()

    def flush(self) -> None:
        pass

    def activate_probe(
        self, scope: str, target: ProbeTarget, **hints: Any
    ) -> Optional[ProbeCallback]:
        raise NotImplementedError()  # pragma: no cover

    def activate_trace(self, scope: str, **hints) -> Optional[TraceCallback]:
        raise NotImplementedError()  # pragma: no cover

    def trace_exception(self) -> None:
        pass


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

    def open(self) -> None:
        self.filename: str = self.env.config.setdefault('sim.log.file', 'sim.log')
        buffering: int = self.env.config.setdefault('sim.log.buffering', -1)
        level: str = self.env.config.setdefault('sim.log.level', 'INFO')
        self.max_level = self.levels[level]
        self.format_str: str = self.env.config.setdefault(
            'sim.log.format', self.default_format
        )
        ts_n, ts_unit = self.env.timescale
        if ts_n == 1:
            self.ts_unit = ts_unit
        else:
            self.ts_unit = f'({ts_n}{ts_unit})'

        if self.filename:
            self.file = open(self.filename, 'w', buffering)
            self.should_close = True
        else:
            self.file = sys.stderr
            self.should_close = False

    def flush(self) -> None:
        self.file.flush()

    def _close(self) -> None:
        if self.should_close:
            self.file.close()

    def remove_files(self) -> None:
        if os.path.isfile(self.filename):
            os.remove(self.filename)

    def is_scope_enabled(self, scope: str, level: Optional[str] = None) -> bool:
        return (level is None or self.levels[level] <= self.max_level) and super(
            LogTracer, self
        ).is_scope_enabled(scope)

    def activate_probe(
        self, scope: str, target: ProbeTarget, **hints: Any
    ) -> Optional[ProbeCallback]:
        level: str = hints.get('level', 'PROBE')
        if not self.is_scope_enabled(scope, level):
            return None
        format_str = partial_format(
            self.format_str, level=level, ts_unit=self.ts_unit, scope=scope
        )

        def probe_callback(value: object) -> None:
            print(format_str.format(ts=self.env.now), value, file=self.file)

        return probe_callback

    def activate_trace(self, scope: str, **hints) -> Optional[TraceCallback]:
        level: str = hints.get('level', 'DEBUG')
        if not self.is_scope_enabled(scope, level):
            return None
        format_str = partial_format(
            self.format_str, level=level, ts_unit=self.ts_unit, scope=scope
        )

        def trace_callback(*value) -> None:
            print(format_str.format(ts=self.env.now), *value, file=self.file)

        return trace_callback

    def trace_exception(self) -> None:
        tb_lines = traceback.format_exception(*sys.exc_info())
        print(
            self.format_str.format(
                level='ERROR', ts=self.env.now, ts_unit=self.ts_unit, scope='Exception'
            ),
            tb_lines[-1],
            '\n',
            *tb_lines,
            file=self.file,
        )


class VCDTracer(Tracer):

    name = 'vcd'

    def open(self) -> None:
        dump_filename: str = self.env.config.setdefault('sim.vcd.dump_file', 'sim.vcd')
        if 'sim.vcd.timescale' in self.env.config:
            vcd_ts_str: str = self.env.config.setdefault(
                'sim.vcd.timescale', self.env.config['sim.timescale']
            )
            mag, unit = parse_time(vcd_ts_str)
        else:
            mag, unit = self.env.timescale
        mag_int = int(mag)
        if mag_int != mag:
            raise ValueError(f'sim.timescale magnitude must be an integer, got {mag}')
        vcd_timescale = mag_int, unit
        self.scale_factor = scale_time(self.env.timescale, vcd_timescale)
        check_values: bool = self.env.config.setdefault('sim.vcd.check_values', True)
        self.dump_file = open(dump_filename, 'w')
        self.vcd = VCDWriter(
            self.dump_file, timescale=vcd_timescale, check_values=check_values
        )
        self.save_filename: str = self.env.config.setdefault(
            'sim.gtkw.file', 'sim.gtkw'
        )
        if self.env.config.setdefault('sim.gtkw.live'):
            from vcd.gtkw import spawn_gtkwave_interactive

            quiet: bool = self.env.config.setdefault('sim.gtkw.quiet', True)
            spawn_gtkwave_interactive(dump_filename, self.save_filename, quiet=quiet)

        start_time: str = self.env.config.setdefault('sim.vcd.start_time', '')
        stop_time: str = self.env.config.setdefault('sim.vcd.stop_time', '')
        t_start = (
            scale_time(parse_time(start_time), self.env.timescale)
            if start_time
            else None
        )
        t_stop = (
            scale_time(parse_time(stop_time), self.env.timescale) if stop_time else None
        )
        self.env.process(self._start_stop(t_start, t_stop))

    def vcd_now(self) -> float:
        return self.env.now * self.scale_factor

    def flush(self) -> None:
        self.dump_file.flush()

    def _close(self) -> None:
        self.vcd.close(self.vcd_now())
        self.dump_file.close()

    def remove_files(self) -> None:
        if os.path.isfile(self.dump_file.name):
            os.remove(self.dump_file.name)
        if os.path.isfile(self.save_filename):
            os.remove(self.save_filename)

    def activate_probe(
        self, scope: str, target: ProbeTarget, **hints: Any
    ) -> Optional[ProbeCallback]:
        assert self.enabled
        var_type: Optional[str] = hints.get('var_type')
        if var_type is None:
            if isinstance(target, (simpy.Container, Pool)):
                if isinstance(target.level, float):
                    var_type = 'real'
                else:
                    var_type = 'integer'
            elif isinstance(target, (simpy.Resource, simpy.Store, Queue)):
                var_type = 'integer'
            else:
                raise ValueError(f'Could not infer VCD var_type for {scope}')

        kwargs = {k: hints[k] for k in ['size', 'init', 'ident'] if k in hints}

        if 'init' not in kwargs:
            if isinstance(target, (simpy.Container, Pool)):
                kwargs['init'] = target.level
            elif isinstance(target, simpy.Resource):
                kwargs['init'] = len(target.users) if target.users else 'z'
            elif isinstance(target, (simpy.Store, Queue)):
                kwargs['init'] = len(target.items)

        parent_scope, name = scope.rsplit('.', 1)
        var = self.vcd.register_var(parent_scope, name, var_type, **kwargs)

        def probe_callback(value: Any) -> None:
            self.vcd.change(var, self.vcd_now(), value)

        return probe_callback

    def activate_trace(self, scope: str, **hints) -> Optional[TraceCallback]:
        assert self.enabled
        var_type = hints['var_type']
        kwargs = {k: hints[k] for k in ['size', 'init', 'ident'] if k in hints}

        parent_scope, name = scope.rsplit('.', 1)
        var = self.vcd.register_var(parent_scope, name, var_type, **kwargs)

        if isinstance(var.size, tuple):

            def trace_callback(*value) -> None:
                self.vcd.change(var, self.vcd_now(), value)

        else:

            def trace_callback(*value) -> None:
                self.vcd.change(var, self.vcd_now(), value[0])

        return trace_callback

    def _start_stop(
        self, t_start: Optional[Union[int, float]], t_stop: Optional[Union[int, float]]
    ) -> Generator[simpy.Timeout, None, None]:
        # Wait for simulation to start to ensure all variable registration is
        # complete before doing and dump_on()/dump_off() calls.
        yield self.env.timeout(0)

        if t_start is None and t_stop is None:
            # |vvvvvvvvvvvvvv|
            pass
        elif t_start is None:
            assert t_stop is not None
            # |vvvvvv--------|
            yield self.env.timeout(t_stop)
            self.vcd.dump_off(self.vcd_now())
        elif t_stop is None:
            # |--------vvvvvv|
            self.vcd.dump_off(self.vcd_now())
            yield self.env.timeout(t_start)
            self.vcd.dump_on(self.vcd_now())
        elif t_start <= t_stop:
            # |---vvvvvv-----|
            self.vcd.dump_off(self.vcd_now())
            yield self.env.timeout(t_start)
            self.vcd.dump_on(self.vcd_now())
            yield self.env.timeout(t_stop - t_start)
            self.vcd.dump_off(self.vcd_now())
        else:
            # |vvv-------vvvv|
            yield self.env.timeout(t_stop)
            self.vcd.dump_off(self.vcd_now())
            yield self.env.timeout(t_start - t_stop)
            self.vcd.dump_on(self.vcd_now())


class SQLiteTracer(Tracer):

    name = 'db'

    def open(self) -> None:
        self.filename: str = self.env.config.setdefault('sim.db.file', 'sim.sqlite')
        self.trace_table: str = self.env.config.setdefault(
            'sim.db.trace_table', 'trace'
        )
        self.remove_files()
        self.db = sqlite3.connect(self.filename)
        self._is_trace_table_created = False

    def _create_trace_table(self) -> None:
        if not self._is_trace_table_created:
            self.db.execute(
                f'CREATE TABLE {self.trace_table} ('
                f'timestamp FLOAT, '
                f'scope TEXT, '
                f'value)'
            )
            self._is_trace_table_created = True

    def flush(self) -> None:
        self.db.commit()

    def _close(self) -> None:
        self.db.commit()
        self.db.close()

    def remove_files(self) -> None:
        if self.filename != ':memory:':
            for filename in [self.filename, f'{self.filename}-journal']:
                if os.path.exists(filename):
                    os.remove(filename)

    def activate_probe(
        self, scope: str, target: ProbeTarget, **hints: Any
    ) -> Optional[ProbeCallback]:
        return self.activate_trace(scope, **hints)

    def activate_trace(self, scope: str, **hints) -> Optional[TraceCallback]:
        assert self.enabled
        self._create_trace_table()
        insert_sql = (
            f'INSERT INTO {self.trace_table} (timestamp, scope, value) VALUES (?, ?, ?)'
        )

        def trace_callback(value) -> None:
            self.db.execute(insert_sql, (self.env.now, scope, value))

        return trace_callback


class TraceManager:
    def __init__(self, env: 'SimEnvironment') -> None:
        self.tracers: List[Tracer] = []
        try:
            self.log_tracer = LogTracer(env)
            self.tracers.append(self.log_tracer)
            self.vcd_tracer = VCDTracer(env)
            self.tracers.append(self.vcd_tracer)
            self.sqlite_tracer = SQLiteTracer(env)
            self.tracers.append(self.sqlite_tracer)
        except BaseException:
            self.close()
            raise

    def flush(self) -> None:
        """Flush all managed tracers instances.

        The effect of flushing is tracer-dependent.

        """
        for tracer in self.tracers:
            if tracer.enabled:
                tracer.flush()

    def close(self) -> None:
        for tracer in self.tracers:
            tracer.close()
            if tracer.enabled and not tracer.persist:
                tracer.remove_files()

    def auto_probe(self, scope: str, target: ProbeTarget, **hints: Any) -> None:
        callbacks: List[ProbeCallback] = []
        for tracer in self.tracers:
            if tracer.name in hints and tracer.is_scope_enabled(scope):
                callback = tracer.activate_probe(scope, target, **hints[tracer.name])
                if callback:
                    callbacks.append(callback)
        if callbacks:
            probe_attach(scope, target, callbacks, **hints)

    def get_trace_function(self, scope: str, **hints) -> Callable[..., None]:
        callbacks = []
        for tracer in self.tracers:
            if tracer.name in hints and tracer.is_scope_enabled(scope):
                callback = tracer.activate_trace(scope, **hints[tracer.name])
                if callback:
                    callbacks.append(callback)

        def trace_function(*value) -> None:
            for callback in callbacks:
                callback(*value)

        return trace_function

    def trace_exception(self) -> None:
        for tracer in self.tracers:
            if tracer.enabled:
                tracer.trace_exception()
