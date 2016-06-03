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
    """Parse a string containing a time magnitude and optional unit.

    :param str time_str: Time string to parse.
    :param str default_unit:
        Default time unit to apply if unit is not present in `time_str`. The
        default unit is only applied if `time_str` does not specify a unit.
    :returns:
        `(magnitude, unit)` tuple where magnitude is numeric (int or float) and
        the unit string is one of "s", "ms", "us", "ns", "ps", or "fs".
    :raises ValueError:
        If the string cannot be parsed or is missing a unit specifier and no
        `default_unit` is specified.

    """
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
    """Scale time values.

    :param tuple from_time: `(magnitude, unit)` tuple to be scaled.
    :param tuple to_time: `(magnitude, unit)` tuple to scale to.
    :returns: Numeric scale factor relating `from_time` to `to_time`.

    """
    from_t, from_u = from_time
    to_t, to_u = to_time
    from_scale = _unit_map[from_u]
    to_scale = _unit_map[to_u]

    scaled = (to_scale / from_scale * from_t) / to_t

    if scaled % 1.0 == 0.0:
        return int(scaled)
    else:
        return scaled
