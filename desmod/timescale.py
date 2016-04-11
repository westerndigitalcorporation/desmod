from __future__ import division
import re

_unit_map = {'s': 1e0,
             'ms': 1e3,
             'us': 1e6,
             'ns': 1e9,
             'ps': 1e12,
             'fs': 1e15}

_num_re = r'[-+]? (?: \d*\.\d+ | \d+\.?\d* ) (?: [eE] [-+]? \d+)?'

_timescale_re = re.compile(
    r'(?P<num>{})?'.format(_num_re) +
    r'\s?' +
    r'(?P<unit> [fpnum]? s)?',
    re.VERBOSE)


def parse_time(time_str, default_unit=None):
    match = _timescale_re.match(time_str)
    if not match or not time_str:
        raise ValueError('Invalid timescale string "{}"'.format(time_str))
    if match.group('num'):
        num_str = match.group('num')
        try:
            num = int(num_str)
        except ValueError:
            num = float(num_str)
    else:
        num = 1

    if match.group('unit'):
        unit = match.group('unit')
    else:
        if default_unit:
            unit = default_unit
        else:
            raise ValueError('No unit specified')
    return num, unit


def scale_time(from_time, to_time):
    from_t, from_u = from_time
    to_t, to_u = to_time
    from_scale = _unit_map[from_u]
    to_scale = _unit_map[to_u]

    scaled = (to_scale / from_scale * from_t) / to_t

    if scaled % 1.0 == 0.0:
        return int(scaled)
    else:
        return scaled
