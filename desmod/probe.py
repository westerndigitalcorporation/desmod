import types

import simpy
import six

from desmod.queue import Queue
from desmod.pool import Pool


def attach(scope, target, callbacks, **hints):
    if isinstance(target, types.MethodType):
        _attach_method(target, callbacks)
    elif isinstance(target, simpy.Container):
        _attach_container_level(target, callbacks)
    elif isinstance(target, simpy.Store):
        _attach_store_items(target, callbacks)
    elif isinstance(target, simpy.Resource):
        if hints.get('trace_queue'):
            _attach_resource_queue(target, callbacks)
        else:
            _attach_resource_users(target, callbacks)
    elif isinstance(target, Queue):
        if hints.get('trace_remaining', False):
            _attach_queue_remaining(target, callbacks)
        else:
            _attach_queue_size(target, callbacks)
    elif isinstance(target, Pool):
        if hints.get('trace_remaining', False):
            _attach_pool_remaining(target, callbacks)
        else:
            _attach_pool_level(target, callbacks)
    else:
        raise TypeError(
            'Cannot probe {} of type {}'.format(scope, type(target)))


def _attach_method(method, callbacks):
    def make_wrapper(func):
        @six.wraps(func)
        def wrapper(*args, **kwargs):
            value = func(*args, **kwargs)
            for callback in callbacks:
                callback(value)
            return value
        return wrapper

    setattr(six.get_method_self(method), method.__func__.__name__,
            make_wrapper(method))


def _attach_container_level(container, callbacks):
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
    def make_wrapper(func):
        @six.wraps(func)
        def wrapper(*args, **kwargs):
            old_users = len(resource.users)
            ret = func(*args, **kwargs)
            new_users = len(resource.users)
            if new_users != old_users:
                for callback in callbacks:
                    callback(new_users)
            return ret
        return wrapper

    resource._do_get = make_wrapper(resource._do_get)
    resource._do_put = make_wrapper(resource._do_put)


def _attach_resource_queue(resource, callbacks):
    def make_wrapper(func):
        @six.wraps(func)
        def wrapper(*args, **kwargs):
            old_queue = len(resource.queue)
            ret = func(*args, **kwargs)
            new_queue = len(resource.queue)
            if new_queue != old_queue:
                for callback in callbacks:
                    callback(new_queue)
            return ret
        return wrapper

    resource.request = make_wrapper(resource.request)
    resource._trigger_put = make_wrapper(resource._trigger_put)


def _attach_queue_size(queue, callbacks):
    def hook():
        for callback in callbacks:
            callback(queue.size)

    queue._put_hook = queue._get_hook = hook


def _attach_queue_remaining(queue, callbacks):
    def hook():
        for callback in callbacks:
            callback(queue.remaining)

    queue._put_hook = queue._get_hook = hook


def _attach_pool_level(pool, callbacks):
    def hook():
        for callback in callbacks:
            callback(pool.level)

    pool._put_hook = pool._get_hook = hook


def _attach_pool_remaining(pool, callbacks):
    def hook():
        for callback in callbacks:
            callback(pool.remaining)

    pool._put_hook = pool._get_hook = hook
