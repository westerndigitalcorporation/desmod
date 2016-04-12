import pytest

from desmod.util import partial_format


@pytest.mark.parametrize('expected, format_str, args, kwargs', [
    ('abc', 'abc', [], {}),
    ('aBc', 'a{b}c', [], {'b': 'B'}),
    ('aBc', 'a{}c', ['B'], {}),
    ('a 1.00 c', 'a {:.{digits}f} c', [1], {'digits': 2}),
    ('a {:.2f} c', 'a {:.{digits}f} c', [], {'digits': 2}),
    ('A{b}C', '{a}{b}{c}', [], {'a': 'A', 'c': 'C'}),
    ('{a}BC{}', '{a}{}{c}{}', ['B'], {'c': 'C'}),
    ('01{2.name}', '{0}{1}{2.name}', [0, 1], {}),
])
def test_partial_format(expected, format_str, args, kwargs):
    result = partial_format(format_str, *args, **kwargs)
    assert expected == result
