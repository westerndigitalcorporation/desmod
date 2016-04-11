import types

import simpy
import six
import vcd


class Probe(object):

    __slots__ = ('scope', 'target', 'hints')

    def __init__(self, parent_scope, name, target, **hints):
        self.scope = parent_scope + '.' + name
        self.target = target
        self.hints = hints

    @property
    def parent_scope(self):
        return self.scope.rsplit('.', 1)[0]

    @property
    def name(self):
        return self.scope.rsplit('.', 1)[1]

    def attach(self, trace_callbacks):
        if isinstance(self.target, types.MethodType):
            _attach_component_method(self.target, trace_callbacks)
        elif isinstance(self.target, simpy.Container):
            _attach_container_level(self.target, trace_callbacks)
        elif isinstance(self.target, simpy.Store):
            _attach_store_items(self.target, trace_callbacks)
        elif isinstance(self.target, simpy.Resource):
            _attach_resource_users(self.target, trace_callbacks)
        else:
            raise TypeError('Cannot probe {} of type {}'
                            .format(self.scope, type(self.target)))

    def detach(self):
        self.attach(trace_callbacks=[])


def _detach_methods(target, method_names):
    for method_name in method_names:
        if six.get_function_closure(getattr(target, method_name)):
            orig_method = six.create_bound_method(
                getattr(type(target), method_name), target)
            setattr(target, method_name, orig_method)


def _attach_component_method(method, callbacks):
    component = six.get_method_self(method)
    _detach_methods(component, [method.__func__.__name__])

    if callbacks:
        def make_wrapper(func):
            @six.wraps(func)
            def wrapper(*args, **kwargs):
                value = func(*args, **kwargs)
                for callback in callbacks:
                    callback(component.env.now, value)
                return value
            return wrapper

        setattr(component, method.__func__.__name__, make_wrapper(method))


def _attach_container_level(container, callbacks):
    _detach_methods(container, ['_do_get', '_do_put'])

    if callbacks:
        def make_wrapper(func):
            @six.wraps(func)
            def wrapper(*args, **kwargs):
                old_level = container._level
                ret = func(*args, **kwargs)
                new_level = container._level
                if new_level != old_level:
                    for callback in callbacks:
                        callback(container._env.now, new_level)
                return ret
            return wrapper

        container._do_get = make_wrapper(container._do_get)
        container._do_put = make_wrapper(container._do_put)


def _attach_store_items(store, callbacks):
    _detach_methods(store, ['_do_get', '_do_put'])
    if callbacks:
        def make_wrapper(func):
            @six.wraps(func)
            def wrapper(*args, **kwargs):
                old_items = len(store.items)
                ret = func(*args, **kwargs)
                new_items = len(store.items)
                if new_items != old_items:
                    for callback in callbacks:
                        callback(store._env.now, new_items)
                return ret
            return wrapper

        store._do_get = make_wrapper(store._do_get)
        store._do_put = make_wrapper(store._do_put)


def _attach_resource_users(resource, callbacks):
    _detach_methods(resource, ['_do_get', '_do_put'])
    if callbacks:
        def make_wrapper(func):
            @six.wraps(func)
            def wrapper(*args, **kwargs):
                old_users = len(resource.users)
                ret = func(*args, **kwargs)
                new_users = len(resource.users)
                if new_users != old_users:
                    value = new_users if new_users else 'z'
                    try:
                        for callback in callbacks:
                            callback(resource._env.now, value)
                    except vcd.VCDPhaseError:
                        pass
                return ret
            return wrapper

        resource._do_get = make_wrapper(resource._do_get)
        resource._do_put = make_wrapper(resource._do_put)
