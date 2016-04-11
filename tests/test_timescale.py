import pytest

from desmod.timescale import parse_time, scale_time


@pytest.mark.parametrize('test_input, expected', [
    ('12 s', (12, 's')),
    ('12s', (12, 's')),
    ('+12s', (12, 's')),
    ('-12s', (-12, 's')),
    ('12.0 s', (12.0, 's')),
    ('12. s', (12.0, 's')),
    ('+12.0 s', (12.0, 's')),
    ('-12.0 s', (-12.0, 's')),
    ('12.000 s', (12.0, 's')),
    ('1.2e1 s', (12.0, 's')),
    ('1.2e+1 s', (12.0, 's')),
    ('1.2e-1 s', (0.12, 's')),
    ('-1.2e-1 s', (-0.12, 's')),
    ('12.s', (12.0, 's')),
    ('12.0s', (12.0, 's')),
    ('12.000s', (12.0, 's')),
    ('1.2e1s', (12.0, 's')),
    ('.12e+2s', (12.0, 's')),
    ('.12s', (0.12, 's')),
    ('12 fs', (12, 'fs')),
    ('12 ps', (12, 'ps')),
    ('12 ns', (12, 'ns')),
    ('12 us', (12, 'us')),
    ('12 ms', (12, 'ms')),
    ('12.0ms', (12.0, 'ms')),
    ('s', (1, 's')),
    ('fs', (1, 'fs')),
])
def test_parse_time(test_input, expected):
    m, u = parse_time(test_input)
    assert (m, u) == expected
    assert isinstance(m, type(expected[0]))


@pytest.mark.parametrize('test_input', [
    '',
    '123       s',
    '123',
    '123.0',
    '123 S',
    '123 Ms',
    '123e1.3 s',
    '+-123 s',
    '123 ks',
    '. s',
    '1-.1 s',
    '1e1.2 s',
])
def test_parse_time_except(test_input):
    with pytest.raises(ValueError) as exc_info:
        parse_time(test_input)
    assert 'float' not in str(exc_info.value)


def test_parse_time_default():
    assert parse_time('123', default_unit='ms') == (123, 'ms')


@pytest.mark.parametrize('input_t, input_tscale, expected', [
    ((1, 'us'), (1, 'us'), 1),
    ((1, 'us'), (10, 'us'), 0.1),
    ((1000, 'us'), (1, 'ms'), 1),
    ((1, 'us'), (100, 'ms'), 1e-5),
    ((50, 'ms'), (1, 'ns'), 50000000),
    ((5.2, 'ms'), (1, 'us'), 5200),
])
def test_scale_time(input_t, input_tscale, expected):
    scaled = scale_time(input_t, input_tscale)
    assert expected == scaled
    assert isinstance(scaled, type(expected))
