import sys
import pytest

from desmod.config import (ConfigError,
                           NamedManager,
                           apply_user_overrides,
                           fuzzy_lookup,
                           factorial_config,
                           parse_user_factor,
                           _safe_eval)


@pytest.fixture
def config():
    return {'foo.bar.baz': 17,
            'foo.bar.biz': 1.23,
            'abc.def.baz': False,
            'a.b.c': 'something',
            'd.e.f': [3, 2, 1],
            'g.h.i': {'a': 1, 'b': 2}}


@pytest.fixture
def named_mgr():
    return NamedManager()


def test_named_reuse(named_mgr):
    named_mgr.name('xxx', [], {'x': 0})
    with pytest.raises(ConfigError):
        named_mgr.name('xxx', [], {'y': 1})
    with pytest.raises(ConfigError):
        named_mgr.resolve('yyy')


def test_named_resolve(named_mgr):
    named_mgr.name('www', [], {'w': 0})
    named_mgr.name('xxx', [], {'x': 1})
    named_mgr.name('yyy', ['xxx', 'www'], {'y': 2})
    named_mgr.name('zzz', ['yyy'], {'z': 3})
    named_mgr.name('qqq', ['zzz'])
    assert named_mgr.resolve('qqq') == {'w': 0, 'x': 1, 'y': 2, 'z': 3}

    assert set(name for name, _, _ in named_mgr.iter()) == {'www', 'xxx',
                                                            'yyy', 'zzz',
                                                            'qqq'}


@pytest.mark.parametrize('fuzzy_key, expected', [
    ('foo', ConfigError),
    ('b.foo', ('a.b.foo', 1)),
    ('d.foo', ('c.d.foo', 3)),
    ('bar', ('a.b.bar', 2)),
    ('o', ('e.f.o', 4)),
    ('.o', ('e.f.o', 4)),
    ('x.y.z', ('x.y.z', 5)),
    ('y.z', ConfigError),
])
def test_fuzzy_lookup(fuzzy_key, expected):
    config = {'a.b.foo': 1,
              'a.b.bar': 2,
              'c.d.foo': 3,
              'e.f.o': 4,
              'x.y.z': 5,
              'w.x.y.z': 6}
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            fuzzy_lookup(config, fuzzy_key)
    else:
        assert fuzzy_lookup(config, fuzzy_key) == expected


def test_user_override(config):
    apply_user_overrides(config, [
        ('biz', '12'),
        ('e.f', 'range(4)'),
        ('g.h.i', 'zip("abc", range(3))'),
    ])
    assert config['foo.bar.biz'] == 12.0
    assert config['d.e.f'] == [0, 1, 2, 3]
    assert config['g.h.i'] == {'a': 0, 'b': 1, 'c': 2}


def test_user_override_type_mismatch(config):
    with pytest.raises(ConfigError):
        apply_user_overrides(config, [('d.e.f', 'os.system("clear")')])


def test_user_override_invalid_value(config):
    with pytest.raises(ConfigError):
        apply_user_overrides(config, [('baz', '1')])


def test_user_override_invalid_key(config):
    with pytest.raises(ConfigError):
        apply_user_overrides(config, [('not.a.key', '1')])


def test_user_override_int(config):
    apply_user_overrides(config, [('bar.baz', '18')])
    assert config['foo.bar.baz'] == 18


def test_user_override_int_invalid(config):
    with pytest.raises(ConfigError):
        apply_user_overrides(config, [('bar.baz', 'eighteen')])


def test_user_override_bool(config):
    apply_user_overrides(config, [('def.baz', '1')])
    assert config['abc.def.baz'] is True
    apply_user_overrides(config, [('def.baz', 'True')])
    assert config['abc.def.baz'] is True
    apply_user_overrides(config, [('def.baz', 'False')])
    assert config['abc.def.baz'] is False


def test_user_override_str(config):
    apply_user_overrides(config, [('a.b.c', 'just a string')])
    assert config['a.b.c'] == 'just a string'


def test_user_override_str_int(config):
    apply_user_overrides(config, [('a.b.c', '123')])
    assert config['a.b.c'] == '123'


@pytest.mark.skipif(hasattr(sys, 'pypy_version_info'),
                    reason="PyPy's eval() mishandles locals dict")
def test_safe_eval_str_builtin_alias():
    assert _safe_eval('oct', str) == 'oct'
    assert _safe_eval('oct') is oct
    with pytest.raises(ConfigError):
        _safe_eval('oct', eval_locals={})
    assert _safe_eval('oct', str, {}) == 'oct'


def test_safe_eval_dict():
    with pytest.raises(ConfigError):
        _safe_eval('oct', coerce_type=dict)


@pytest.mark.parametrize('user_keys, user_exprs, expected', [
    ('foo', '1,2,3', [['a.b.foo'], [[1], [2], [3]]]),
    ('bar', '1.2, 3, 4.5', [['a.b.bar'], [[1.2], [3.0], [4.5]]]),
    ('b.baz', '"abc"', [['a.b.baz'], [['a'], ['b'], ['c']]]),
    ('b.baz', '"abc","def"', [['a.b.baz'], [['abc'], ['def']]]),
    ('d.baz', '1, "y", 0', [['c.d.baz'], [[True], [True], [False]]]),
    ('foo,bar', '(1,1),(2,2)', [['a.b.foo', 'a.b.bar'],
                                [[1, 1.0], [2, 2.0]]]),
])
def test_parse_user_factor(user_keys, user_exprs, expected):
    config = {
        'a.b.foo': 1,
        'a.b.bar': 2.0,
        'a.b.baz': 'three',
        'c.d.baz': True,
    }

    factor = parse_user_factor(config, user_keys, user_exprs)
    assert expected == factor
    assert all(isinstance(value, type(expected_value))
               for value, expected_value in zip(factor[1], expected[1]))


@pytest.mark.parametrize('user_keys, user_exprs, err_str', [
    ('baz', 'True, False', 'Ambiguous'),
    ('foo', '"one", "two"', 'coerce'),
    ('foo', '1', 'sequence'),
])
def test_parse_user_factor_invalid(user_keys, user_exprs, err_str):
    config = {
        'a.b.foo': 1,
        'a.b.bar': 2.0,
        'a.b.baz': 'three',
        'c.d.baz': True,
    }
    with pytest.raises(ConfigError) as e:
        parse_user_factor(config, user_keys, user_exprs)
    print(e)
    assert err_str in str(e)


def test_factorial_config():
    factors = [
        (['k0', 'k1'], [[0, 1], [2, 3]]),
        (['k2'], [[4], [5], [6]]),
    ]

    expected = [{'k0': 0, 'k1': 1, 'k2': 4},
                {'k0': 0, 'k1': 1, 'k2': 5},
                {'k0': 0, 'k1': 1, 'k2': 6},
                {'k0': 2, 'k1': 3, 'k2': 4},
                {'k0': 2, 'k1': 3, 'k2': 5},
                {'k0': 2, 'k1': 3, 'k2': 6}]

    assert list(factorial_config({}, factors)) == expected


def test_factorial_config_special():
    factors = [
        (['k0', 'k1'], [[0, 1], [2, 3]]),
        (['k2'], [[4], [5], [6]]),
    ]

    expected = [
        {'k0': 0, 'k1': 1, 'k2': 4, 'special': [
            ['k0', 0], ['k1', 1], ['k2', 4]]},
        {'k0': 0, 'k1': 1, 'k2': 5, 'special': [
            ['k0', 0], ['k1', 1], ['k2', 5]]},
        {'k0': 0, 'k1': 1, 'k2': 6, 'special': [
            ['k0', 0], ['k1', 1], ['k2', 6]]},
        {'k0': 2, 'k1': 3, 'k2': 4, 'special': [
            ['k0', 2], ['k1', 3], ['k2', 4]]},
        {'k0': 2, 'k1': 3, 'k2': 5, 'special': [
            ['k0', 2], ['k1', 3], ['k2', 5]]},
        {'k0': 2, 'k1': 3, 'k2': 6, 'special': [
            ['k0', 2], ['k1', 3], ['k2', 6]]}]

    fc = factorial_config({}, factors, 'special')
    assert list(fc) == expected
