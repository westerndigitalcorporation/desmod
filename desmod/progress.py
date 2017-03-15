from __future__ import print_function, division
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timedelta
import sys
import timeit

try:
    import progressbar
except ImportError:
    progressbar = None
try:
    import colorama
except ImportError:
    colorama = None

from desmod.timescale import parse_time, scale_time


@contextmanager
def standalone_progress_manager(env):
    enabled = env.config.setdefault('sim.progress.enable', False)
    max_width = env.config.setdefault('sim.progress.max_width')
    period_s = _get_interval_period_s(env.config)

    if enabled:
        if sys.stderr.isatty() and progressbar:
            pbar = _get_standalone_pbar(env, max_width, sys.stderr)
            env.process(_standalone_pbar_process(env, pbar, period_s))
            try:
                yield None
            finally:
                pbar.finish()
        else:
            env.process(_standalone_display_process(env, period_s, sys.stderr))
            try:
                yield None
            finally:
                _print_progress(env.sim_index, env.now, env.now, env.timescale,
                                end='\n', fd=sys.stderr)
    else:
        yield None


def _get_interval_period_s(config):
    period_str = config.setdefault('sim.progress.update_period', '1 s')
    return scale_time(parse_time(period_str), (1, 's'))


def _standalone_display_process(env, period_s, fd):
    interval = 1
    end = '\r' if fd.isatty() else '\n'
    while True:
        sim_index, now, t_stop, timescale = env.get_progress()
        _print_progress(sim_index, now, t_stop, timescale, end=end, fd=fd)
        t0 = timeit.default_timer()
        yield env.timeout(interval)
        t1 = timeit.default_timer()
        interval *= period_s / (t1 - t0)


def _print_progress(sim_index, now, t_stop, timescale, end, fd):
    parts = []
    if sim_index:
        parts.append('Sim ' + str(sim_index))
    magnitude, units = timescale
    if magnitude == 1:
        parts.append('{:6.0f} {}'.format(now, units))
    else:
        parts.append('{}x{:6.0f} {}'.format(magnitude, now, units))
    if t_stop:
        parts.append('({:.0f}%)'.format(100 * now / t_stop))
    else:
        parts.append('(N/A%)')
    print(*parts, end=end, file=fd)
    fd.flush()


def _get_standalone_pbar(env, max_width, fd):
    pbar = progressbar.ProgressBar(
        fd=fd,
        min_value=0,
        max_value=progressbar.UnknownLength,
        widgets=_get_progressbar_widgets(env.sim_index, env.timescale,
                                         know_stop_time=False))

    if max_width and pbar.term_width > max_width:
        pbar.term_width = max_width

    return pbar


def _standalone_pbar_process(env, pbar, period_s):
    interval = 1
    while True:
        sim_index, now, t_stop, timescale = env.get_progress()
        if t_stop and pbar.max_value != t_stop:
            pbar.max_value = t_stop
            pbar.widgets = _get_progressbar_widgets(sim_index, timescale,
                                                    know_stop_time=True)
        pbar.update(now)
        t0 = timeit.default_timer()
        yield env.timeout(interval)
        t1 = timeit.default_timer()
        interval *= period_s / (t1 - t0)


def _get_progressbar_widgets(sim_index, timescale, know_stop_time):
    widgets = []

    if sim_index is not None:
        widgets.append('Sim {:3}|'.format(sim_index))

    magnitude, units = timescale
    if magnitude == 1:
        sim_time_format = '%(value)6.0f {}|'.format(units)
    else:
        sim_time_format = '{}x%(value)6.0f {}|'.format(magnitude, units)
    widgets.append(progressbar.FormatLabel(sim_time_format))

    widgets.append(progressbar.Percentage())

    if know_stop_time:
        widgets.append(progressbar.Bar())
    else:
        widgets.append(progressbar.BouncingBar())

    widgets.append(progressbar.ETA())

    return widgets


def get_multi_progress_manager(progress_queue):
    @contextmanager
    def progress_producer(env):
        if progress_queue:
            period_s = _get_interval_period_s(env.config)
            env.process(
                _progress_enqueue_process(env, period_s, progress_queue))
            try:
                yield None
            finally:
                progress_queue.put((env.sim_index, env.now, env.now,
                                    env.timescale))
        else:
            yield None

    return progress_producer


def _progress_enqueue_process(env, period_s, progress_queue):
    interval = 1
    while True:
        progress_queue.put(env.get_progress())
        t0 = timeit.default_timer()
        yield env.timeout(interval)
        t1 = timeit.default_timer()
        interval *= period_s / (t1 - t0)


def consume_multi_progress(progress_queue, num_workers, num_simulations,
                           max_width):
    fd = sys.stderr
    try:
        if fd.isatty():
            if progressbar and colorama:
                _consume_multi_display_multi_pbar(
                    progress_queue, num_workers, num_simulations, max_width,
                    fd)
            elif progressbar:
                _consume_multi_display_single_pbar(
                    progress_queue, num_workers, num_simulations, max_width,
                    fd)
            else:
                _consume_multi_display_simple(
                    progress_queue, num_workers, num_simulations, max_width,
                    fd)
        else:
            _consume_multi_display_simple(
                progress_queue, num_workers, num_simulations, max_width, fd)
    except KeyboardInterrupt:
        pass


def _consume_multi_display_simple(progress_queue, num_workers, num_simulations,
                                  max_width, fd):
    start_date = datetime.now()
    isatty = fd.isatty()
    end = '\r' if isatty else '\n'
    try:
        completed = set()
        _print_simple(len(completed), num_simulations, timedelta(), end, fd)
        last_print_date = start_date
        while len(completed) < num_simulations:
            sim_index, now, t_stop, timescale = progress_queue.get()
            now_date = datetime.now()
            td = now_date - start_date
            td_print = now_date - last_print_date
            if now == t_stop:
                completed.add(sim_index)
                _print_simple(len(completed), num_simulations, td, end, fd)
                last_print_date = now_date
            elif isatty and td_print.total_seconds() >= 1:
                _print_simple(len(completed), num_simulations, td, end, fd)
                last_print_date = now_date
    finally:
        if isatty:
            print(file=fd)


def _print_simple(num_completed, num_simulations, td, end, fd):
    if fd.closed:
        return
    print(timedelta(td.days, td.seconds),
          num_completed, 'of', num_simulations, 'simulations',
          '({:.0%})'.format(num_completed / num_simulations),
          end=end, file=fd)
    fd.flush()


def _consume_multi_display_single_pbar(progress_queue, num_workers,
                                       num_simulations, max_width, fd):
    overall_pbar = _get_overall_pbar(num_simulations, max_width, fd=fd)
    try:
        completed = set()
        while len(completed) < num_simulations:
            sim_index, now, t_stop, timescale = progress_queue.get()
            if now == t_stop:
                completed.add(sim_index)
                overall_pbar.update(len(completed))
    finally:
        overall_pbar.finish()


def _consume_multi_display_multi_pbar(progress_queue, num_workers,
                                      num_simulations, max_width, fd):
    # In order to display multiple progress bars, we need to manipulate the
    # terminal/console to move up lines. Colorama is used to wrap stderr such
    # that ANSI escape sequences are mapped to equivalent win32 API calls.
    fd = colorama.AnsiToWin32(fd).stream

    def ansi_up(n):
        return b'\x1b[{}A'.decode('latin1').format(n)

    ansi_bold = b'\x1b[1m'.decode('latin1')
    ansi_norm = b'\x1b[0m'.decode('latin1')

    overall_pbar = _get_overall_pbar(num_simulations, max_width, fd)

    try:
        worker_progress = OrderedDict()
        completed = set()
        while len(completed) < num_simulations:
            sim_index, now, t_stop, timescale = progress_queue.get()

            if now == t_stop:
                completed.add(sim_index)

            if worker_progress:
                print(ansi_up(len(worker_progress)), end='', file=fd)

            if sim_index in worker_progress:
                for pindex, pbar in worker_progress.items():
                    if sim_index == pindex and pbar:
                        if now == t_stop:
                            pbar.finish()
                            worker_progress[sim_index] = None
                        else:
                            if t_stop and pbar.max_value != t_stop:
                                pbar.max_value = t_stop
                                pbar.widgets = _get_progressbar_widgets(
                                    sim_index, timescale, know_stop_time=True)
                            pbar.update(now)
                            print(file=fd)
                    else:
                        print(file=fd)
            else:
                for pindex, pbar in worker_progress.items():
                    if pbar is None:
                        worker_progress.pop(pindex)
                        break
                print('\n' * len(worker_progress), file=fd)
                pbar = progressbar.ProgressBar(
                    fd=fd,
                    term_width=overall_pbar.term_width,
                    min_value=0,
                    max_value=(progressbar.UnknownLength
                               if t_stop is None else t_stop),
                    widgets=_get_progressbar_widgets(
                        sim_index, timescale,
                        know_stop_time=t_stop is not None))
                worker_progress[sim_index] = pbar

            print(ansi_bold, end='', file=fd)
            overall_pbar.update(len(completed))
            print(ansi_norm, end='', file=fd)
    finally:
        print(ansi_bold, end='', file=fd)
        overall_pbar.finish()
        print(ansi_norm, end='', file=fd)


def _get_overall_pbar(num_simulations, max_width, fd):
    pbar = progressbar.ProgressBar(
        fd=fd,
        min_value=0,
        max_value=num_simulations,
        widgets=[progressbar.FormatLabel('%(value)s of %(max_value)s '),
                 'simulations (',
                 progressbar.Percentage(),
                 ') ',
                 progressbar.Bar(),
                 progressbar.ETA()])

    if max_width and pbar.term_width > max_width:
        pbar.term_width = max_width

    return pbar
