"""Tools for managing simulation configurations.

Each simulation requires a configuration dictionary that defines various
configuration values for both the simulation (`desmod`) and the user model. The
configuration dictionary is flat, but the keys use a dotted notation, similar
to :class:`Component` scopes, that allows for different namespaces to exist
within the [flat] configuration dictionary.

Several configuration key/values are required by desmod itself. These
configuration keys are prefixed with 'sim.'; for example: 'sim.duration' and
'sim.seed'.

Models may define their own configuration key/values, but should avoid using
the 'sim.` prefix.

The :class:`NamedManager` class provides a mechanism for defining named
groupings of configuration values. These named configuration groups allow
quick configuration of multiple values. Configuration groups are also
composable: a configuration group can be defined to depend on several other
configuration groups.

Most functions in this module are provided to support building user interfaces
for configuring a model.

"""
from copy import deepcopy
from collections import Sequence
from itertools import product

import six
from six.moves import builtins
from six.moves import zip


class ConfigError(Exception):
    """Exception raised for a variety of configuration errors."""


class NamedManager(object):
    """Manage named configuration groups.

    Any number of named configuration groups can be specified using the
    :meth:`name()` method. The :meth:`resolve()` method is used to compose a
    fully-resolved configuration based on one or more configuration group
    names.

    """
    def __init__(self):
        self._named_configs = {}

    def name(self, name, deps, cfg=None):
        """Declare a new configuration group.

        A configuration group consists of a name, a list of dependencies, and a
        dictionary of configuration key/values. This function declares a new
        configuration group that may be later resolved with :meth:`resolve()`.

        :param str name: Name of new configuration group.
        :param list deps: List of configuration group dependencies.
        :param dict cfg: Configuration key/values.

        """
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
    """Apply user-provided overrides to a configuration.

    The user-provided `overrides` list are first verified for validity and
    then applied to the the provided `config` dictionary.

    Each user-provided key must already exist in `config`. The
    :func:`fuzzy_lookup()` function is used to verify that the user-provided
    key exists unambiguously in `config`.

    The user-provided value expressions are evaluated against a safe local
    environment using :func:`eval()`. The type of the resulting value must be
    type-compatible with the existing (default) value in `config`.

    :param dict config: Configuration dictionary to modify.
    :param list overrides:
        List of user-provided (key, value expression) tuples.
    :param dict eval_locals:
        Optional dictionary of locals to use with :func:`eval()`. A safe and
        useful set of locals is provided by default.

    """
    for user_key, user_expr in overrides:
        key, current_value = fuzzy_lookup(config, user_key)
        value = _safe_eval(user_expr, type(current_value), eval_locals)
        config[key] = value


def parse_user_factors(config, user_factors, eval_locals=None):
    """Safely parse user-provided configuration factors.

    A configuration factor consists of an n-tuple of configuration keys along
    with a list of corresponding n-tuples of values. Configuration factors are
    used by :func:`~desmod.simulation.simulate_factors()` to run multiple
    simulations to explore a subset of the model's configuration space.

    :param dict config:
        The configuration dictionary is used to check the keys and values of
        the user-provided factors. The dictionary is not modified.
    :param user_factors:
        Sequence of `(user_keys, user_expressions)` tuples. See
        :func:`parse_user_factor()` for more detail on user keys and
        expressions.
    :param dict eval_locals:
        Optional dictionary of locals used when :func:`eval()`-ing user
        expressions.
    :returns:
        List of keys, values pairs. The returned list of factors is suitable
        for assigning to `config['sim.factors']`.
    :raises `desmod.config.ConfigError`: For invalid user keys or expressions.

    """
    return [parse_user_factor(config, user_keys, user_exprs, eval_locals)
            for user_keys, user_exprs in user_factors]


def parse_user_factor(config, user_keys, user_exprs, eval_locals=None):
    """Safely parse a user-provided configuration factor.

    Example:

        >>> config = {'a.b.x': 0,
                      'a.b.y': True,
                      'a.b.z': 'something'}
        >>> parse_user_factor(config, 'x,y', '(1,True), (2,False), (3,True)')
        [['a.b.x', 'a.b.y'], [[1, True], [2, False], [3, True]]]

    :param dict config:
        The configuration dictionary is used to check the keys and values of
        the user-provided factors. The dictionary is not modified.
    :param str user_keys:
        String of comma-separated configuration keys of the factor. The keys
        may be fuzzy (i.e. valid for use with :func:`fuzzy_lookup()`), but note
        that the returned keys will always be fully-qualified (non-fuzzy).
    :param str user_exprs:
        User-provided Python expressions string. The expressions string is
        evaluated using :func:`eval()` with, by default, a safe locals
        dictionary. The expressions string must evaluate to a sequence of
        n-tuples where `n` is the number of keys provided in `user_keys`.
        Further, the elements of each n-tuple must be type-compatible with the
        existing (default) values in the `config` dict.
    :param dict eval_locals:
        Optional dictionary of locals used when :func:`eval()`-ing user
        expressions.

    :returns:
        A config factor: a pair (2-list) of keys and values lists.

        .. Note:: All sequences in the returned factor are expressed as lists,
                  not tuples. This is done to improve YAML serialization.

    :raises `desmod.config.ConfigError`: For invalid keys or value expressions.

    """
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
    """Generate configurations from base config and config factors.

    :param dict base_config:
        Configuration dictionary that the generated configuration dictionaries
        are based on. This dict is not modified; generated config dicts are
        created with :func:`copy.deepcopy()`.
    :param list factors:
        Sequence of one or more configuration factors. Each configuration
        factor is a 2-tuple of keys and values lists.
    :param str special_key:
        When specified, a key/value will be inserted into the generated
        configuration dicts that identifies the "special" (unique) key/value
        combinations of the specified `factors` used in the config dict.
    :yields:
        Configuration dictionaries with the cartesian product of the provided
        `factors` applied. I.e. each yielded config dict will have a unique
        combination of the `factors`.

    """
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
    """Lookup a config key/value using a partially specified (fuzzy) key.

    The lookup will succeed iff the provided `fuzzy_key` unambiguously matches
    the tail of a [fully-qualified] key in the `config` dict.

    :param dict config: Configuration dict in which to lookup `fuzzy_key`.
    :param str fuzzy_key: Partially specified key to lookup in `config`.
    :returns:
        `(key, value)` tuple. The returned key is the regular, fully-qualified
        key name, not the provided `fuzzy_key`.
    :raises `desmod.config.ConfigError`: For non-matching `fuzzy_key`.

    """
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
    'tuple', 'tuple', 'zip', 'True', 'False',
]

_default_eval_locals = {name: getattr(builtins, name)
                        for name in _safe_builtins
                        if hasattr(builtins, name)}


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
