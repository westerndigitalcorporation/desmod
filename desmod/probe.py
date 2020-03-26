from functools import wraps
from types import MethodType
from typing import Any, Callable, Iterable, Union

import simpy

from desmod.pool import Pool
from desmod.queue import ItemType, Queue

ProbeCallback = Callable[[Any], None]
ProbeCallbacks = Iterable[ProbeCallback]
ProbeTarget = Union[
    Pool, Queue[ItemType], simpy.Resource, simpy.Store, simpy.Container, MethodType
]


def attach(
    scope: str, target: ProbeTarget, callbacks: ProbeCallbacks, **hints: Any
) -> None:
    if isinstance(target, MethodType):
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
        raise TypeError(f'Cannot probe {scope} of type {type(target)}')


def _attach_method(method: MethodType, callbacks: ProbeCallbacks) -> None:
    def make_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            value = func(*args, **kwargs)
            for callback in callbacks:
                callback(value)
            return value

        return wrapper

    setattr(method.__self__, method.__func__.__name__, make_wrapper(method))


def _attach_container_level(
    container: simpy.Container, callbacks: ProbeCallbacks
) -> None:
    def make_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            old_level = container._level
            ret = func(*args, **kwargs)
            new_level = container._level
            if new_level != old_level:
                for callback in callbacks:
                    callback(new_level)
            return ret

        return wrapper

    container._do_get = make_wrapper(container._do_get)  # type: ignore
    container._do_put = make_wrapper(container._do_put)  # type: ignore


def _attach_store_items(store: simpy.Store, callbacks: ProbeCallbacks) -> None:
    def make_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            old_items = len(store.items)
            ret = func(*args, **kwargs)
            new_items = len(store.items)
            if new_items != old_items:
                for callback in callbacks:
                    callback(new_items)
            return ret

        return wrapper

    store._do_get = make_wrapper(store._do_get)  # type: ignore
    store._do_put = make_wrapper(store._do_put)  # type: ignore


def _attach_resource_users(resource: simpy.Resource, callbacks: ProbeCallbacks) -> None:
    def make_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            old_users = len(resource.users)
            ret = func(*args, **kwargs)
            new_users = len(resource.users)
            if new_users != old_users:
                for callback in callbacks:
                    callback(new_users)
            return ret

        return wrapper

    resource._do_get = make_wrapper(resource._do_get)  # type: ignore
    resource._do_put = make_wrapper(resource._do_put)  # type: ignore


def _attach_resource_queue(resource: simpy.Resource, callbacks: ProbeCallbacks) -> None:
    def make_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            old_queue = len(resource.queue)
            ret = func(*args, **kwargs)
            new_queue = len(resource.queue)
            if new_queue != old_queue:
                for callback in callbacks:
                    callback(new_queue)
            return ret

        return wrapper

    resource.request = make_wrapper(resource.request)  # type: ignore
    resource._trigger_put = make_wrapper(resource._trigger_put)  # type: ignore


def _attach_queue_size(queue: Queue[ItemType], callbacks: ProbeCallbacks) -> None:
    def hook():
        for callback in callbacks:
            callback(queue.size)

    queue._put_hook = queue._get_hook = hook


def _attach_queue_remaining(queue: Queue[ItemType], callbacks: ProbeCallbacks) -> None:
    def hook():
        for callback in callbacks:
            callback(queue.remaining)

    queue._put_hook = queue._get_hook = hook


def _attach_pool_level(pool: Pool, callbacks: ProbeCallbacks) -> None:
    def hook():
        for callback in callbacks:
            callback(pool.level)

    pool._put_hook = pool._get_hook = hook


def _attach_pool_remaining(pool: Pool, callbacks: ProbeCallbacks) -> None:
    def hook():
        for callback in callbacks:
            callback(pool.remaining)

    pool._put_hook = pool._get_hook = hook
