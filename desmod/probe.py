import types

import simpy
import six
import vcd

from desmod.queue import Queue


def attach(scope, target, callbacks, **hints):
    if isinstance(target, types.MethodType):
        _attach_component_method(target, callbacks)
    elif isinstance(target, simpy.Container):
        _attach_container_level(target, callbacks)
    elif isinstance(target, simpy.Store):
        _attach_store_items(target, callbacks)
    elif isinstance(target, simpy.Resource):
        _attach_resource_users(target, callbacks)
    elif isinstance(target, Queue):
        if hints.get('trace_remaining', False):
            _attach_queue_remaining(target, callbacks)
        else:
            _attach_queue_size(target, callbacks)
    else:
        raise TypeError(
            'Cannot probe {} of type {}'.format(scope, type(target)))


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
                    callback(value)
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
                        callback(new_level)
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
                        callback(new_items)
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
                            callback(value)
                    except vcd.VCDPhaseError:
                        pass
                return ret
            return wrapper

        resource._do_get = make_wrapper(resource._do_get)
        resource._do_put = make_wrapper(resource._do_put)


def _attach_queue_size(queue, callbacks):
    if callbacks:
        def hook():
            for callback in callbacks:
                callback(queue.size)

        queue._put_hook = queue._get_hook = hook
    else:
        queue._put_hook = queue._get_hook = None


def _attach_queue_remaining(queue, callbacks):
    if callbacks:
        def hook():
            for callback in callbacks:
                callback(queue.remaining)

        queue._put_hook = queue._get_hook = hook
    else:
        queue._put_hook = queue._get_hook = None
