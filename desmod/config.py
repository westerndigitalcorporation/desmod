import six
from six.moves import builtins


class ConfigError(Exception):
    pass


def apply_user_overrides(config, overrides, eval_locals=None):
    for user_key, user_expr in overrides:
        key, current_value = _fuzzy_lookup(config, user_key)
        value = _safe_eval(user_expr, type(current_value), eval_locals)
        config[key] = value


def _fuzzy_lookup(config, fuzzy_key):
    try:
        return fuzzy_key, config[fuzzy_key]
    except KeyError:
        match_keys = [k for k in config if k.endswith(fuzzy_key)]
        if len(match_keys) == 1:
            return match_keys[0], config[match_keys[0]]
        elif not match_keys:
            raise ConfigError('Invalid config key "{}"'.format(fuzzy_key))
        else:
            raise ConfigError(
                'Ambiguous config key "{}"; possible matches: {}'.format(
                    fuzzy_key, ', '.join(match_keys)))


_safe_builtins = [
    'abs', 'bin', 'bool', 'dict', 'float', 'frozenset', 'hex', 'int', 'len',
    'list', 'max', 'min', 'oct', 'ord', 'range', 'round', 'set', 'str', 'sum',
    'tuple', 'tuple', 'zip',
]

_default_eval_locals = {name: getattr(builtins, name)
                        for name in _safe_builtins}


def _safe_eval(expr, coerce_type=None, eval_locals=None):
    if eval_locals is None:
        eval_locals = _default_eval_locals
    try:
        value = eval(expr, {'__builtins__': None}, eval_locals)
    except:
        if coerce_type and issubclass(coerce_type, six.string_types):
            value = expr
        else:
            raise ConfigError(
                'Failed evaluation of expression "{}"'.format(expr))

    if coerce_type:
        if expr in eval_locals and not isinstance(value, coerce_type):
            value = expr
        if not isinstance(value, coerce_type):
            try:
                value = coerce_type(value)
            except (ValueError, TypeError):
                raise ConfigError(
                    'Failed to coerce expression {} to {}'.format(
                        _quote_expr(expr), coerce_type.__name__))
    return value


def _quote_expr(expr):
    quote_char = "'" if expr.startswith('"') else '"'
    return ''.join([quote_char, expr, quote_char])
