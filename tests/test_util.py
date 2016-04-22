import pytest

from desmod.util import partial_format


@pytest.mark.parametrize('expected, format_str, kwargs', [
    ('abc', 'abc', {}),
    ('aBc', 'a{b}c', {'b': 'B'}),
    ('a{b!r}c', 'a{b!r}c', {}),
    ("a'B'c", 'a{b!r}c', {'b': 'B'}),
    ('a {:.2f} c', 'a {:.{digits}f} c', {'digits': 2}),
    ('A{b}C', '{a}{b}{c}', {'a': 'A', 'c': 'C'}),
])
def test_partial_format(expected, format_str, kwargs):
    assert expected == partial_format(format_str, **kwargs)
