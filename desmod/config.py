from copy import deepcopy
from collections import Sequence
from itertools import product

import six
from six.moves import builtins
from six.moves import zip


class ConfigError(Exception):
    pass


class NamedManager(object):
    """Manage named configurations.

    Any number of named configurations can be input using the name() method.
    The resolve() method is used to compose a fully resolved configuration
    based on one or more named configurations.

    """
    def __init__(self):
        self._named_configs = {}

    def name(self, name, deps, cfg=None):
        """Name a new config and its dependencies."""
        if name in self._named_configs:
            raise ConfigError('name already used: {}'.format(name))
        if cfg is None:
            cfg = {}
        self._named_configs[name] = (deps, cfg)

    def resolve(self, *names):
        """Resolve named configs into a new config object."""
        resolved = {}
        self._resolve(resolved, *names)
        return resolved

    def _resolve(self, resolved, *names):
        for name in names:
            if name not in self._named_configs:
                raise ConfigError('unknown named config: {}'.format(name))
            deps, cfg = self._named_configs[name]
            self._resolve(resolved, *deps)
            resolved.update(cfg)

    def iter(self):
        """Iterate named config (name, deps, cfg) tuples."""
        for name, (deps, cfg) in self._named_configs.items():
            yield name, deps, cfg


def apply_user_overrides(config, overrides, eval_locals=None):
    for user_key, user_expr in overrides:
        key, current_value = fuzzy_lookup(config, user_key)
        value = _safe_eval(user_expr, type(current_value), eval_locals)
        config[key] = value


def parse_user_factors(config, user_factors, eval_locals=None):
    return [parse_user_factor(config, user_keys, user_exprs, eval_locals)
            for user_keys, user_exprs in user_factors]


def parse_user_factor(config, user_keys, user_exprs, eval_locals=None):
    current = [fuzzy_lookup(config, user_key.strip())
               for user_key in user_keys.split(',')]
    user_values = _safe_eval(user_exprs, eval_locals=eval_locals)
    values = []
    if not isinstance(user_values, Sequence):
        raise ConfigError(
            'Factor value not a sequence "{}"'.format(user_values))
    for user_items in user_values:
        if len(current) == 1:
            user_items = [user_items]
        items = []
        for (key, current_value), item in zip(current, user_items):
            current_type = type(current_value)
            if not isinstance(item, current_type):
                try:
                    item = current_type(item)
                except (ValueError, TypeError):
                    raise ConfigError('Failed to coerce {} to {}'.format(
                        item, current_type.__name__))
            items.append(item)
        values.append(items)
    return [[key for key, _ in current], values]


def factorial_config(base_config, factors, special_key=None):
    unrolled_factors = []
    for keys, values_list in factors:
        unrolled_factors.append([(keys, values) for values in values_list])

    for keys_values_lists in product(*unrolled_factors):
        config = deepcopy(base_config)
        special = []
        if special_key:
            config[special_key] = special
        for keys, values in keys_values_lists:
            for key, value in zip(keys, values):
                config[key] = value
                if special_key:
                    special.append([key, value])
        yield config


def get_short_special(special):
    short_special = []
    for key, value in special:
        key_parts = key.split('.')
        for i in reversed(range(len(key_parts))):
            short_key = '.'.join(key_parts[i:])
            if all(k == key or not k.endswith(short_key) for k, _ in special):
                short_special.append((short_key, value))
                break
    return short_special


def fuzzy_lookup(config, fuzzy_key):
    try:
        return fuzzy_key, config[fuzzy_key]
    except KeyError:
        suffix_matches = []
        split_matches = []
        for k in config:
            if k.rsplit('.', 1)[-1] == fuzzy_key:
                split_matches.append(k)
            elif k.endswith(fuzzy_key):
                suffix_matches.append(k)
        if len(split_matches) == 1:
            k = split_matches[0]
            return k, config[k]
        elif len(suffix_matches) == 1:
            k = suffix_matches[0]
            return k, config[k]
        elif not suffix_matches + split_matches:
            raise ConfigError('Invalid config key "{}"'.format(fuzzy_key))
        else:
            raise ConfigError(
                'Ambiguous config key "{}"; possible matches: {}'.format(
                    fuzzy_key, ', '.join(split_matches + suffix_matches)))


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
