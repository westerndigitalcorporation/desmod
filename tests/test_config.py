import pytest

from desmod.config import ConfigError, apply_user_overrides, _safe_eval


@pytest.fixture
def config():
    return {'foo.bar.baz': 17,
            'foo.bar.biz': 1.23,
            'abc.def.baz': False,
            'a.b.c': 'something',
            'd.e.f': [3, 2, 1],
            'g.h.i': {'a': 1, 'b': 2}}


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


def test_user_override_str(config):
    apply_user_overrides(config, [('a.b.c', 'just a string')])
    assert config['a.b.c'] == 'just a string'


def test_user_override_str_int(config):
    apply_user_overrides(config, [('a.b.c', '123')])
    assert config['a.b.c'] == '123'


def test_safe_eval_str_builtin_alias():
    assert _safe_eval('oct', str) == 'oct'
    assert _safe_eval('oct') is oct
    with pytest.raises(ConfigError):
        _safe_eval('oct', eval_locals={})
    assert _safe_eval('oct', str, {}) == 'oct'


def test_safe_eval_dict():
    with pytest.raises(ConfigError):
        _safe_eval('oct', coerce_type=dict)
