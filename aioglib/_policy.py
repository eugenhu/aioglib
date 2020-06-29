import asyncio
from gi.repository import GLib
import threading
from typing import Optional
import sys

from . import _loop
from . import _helpers

__all__ = [
    'get_event_loop',
    'set_event_loop',
    'new_event_loop',
    'get_default_loop',
    'get_running_loop',
    'GLibEventLoopPolicy',
]


def get_event_loop() -> _loop.GLibEventLoop:
    """If called from the main thread, return a GLibEventLoop for the global default context. Otherwise,
    return a GLibEventLoop for the thread default context, if one has been set, otherwise for the global
    default context."""
    if threading.current_thread() is threading.main_thread():
        context = GLib.MainContext.default()
    else:
        context = GLib.MainContext.get_thread_default() or GLib.MainContext.default()

    return _loop.GLibEventLoop(context)


def set_event_loop(loop: _loop.GLibEventLoop) -> None:
    raise RuntimeError("set_event_loop() not supported")


def new_event_loop() -> _loop.GLibEventLoop:
    """Create a new GLib.MainContext and return a GLibEventLoop wrapping the new context."""
    context = GLib.MainContext()
    return _loop.GLibEventLoop(context)


def get_default_loop() -> _loop.GLibEventLoop:
    """Return a GLibEventLoop for the global default context."""
    context = GLib.MainContext.default()
    return _loop.GLibEventLoop(context)


def get_running_loop() -> _loop.GLibEventLoop:
    """Return a GLibEventLoop for the context of the currently dispatching GLib.Source."""
    loop = _get_running_loop()
    if loop is None:
        raise RuntimeError('no running event loop')

    return loop


def _get_running_loop() -> Optional[_loop.GLibEventLoop]:
    running_context = _helpers.get_running_context()
    if running_context is None:
        return None

    return _loop.GLibEventLoop(running_context)


class GLibEventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    def get_event_loop(self) -> _loop.GLibEventLoop:
        return get_event_loop()

    def set_event_loop(self, loop: _loop.GLibEventLoop) -> None:
        return set_event_loop(loop)

    def new_event_loop(self) -> _loop.GLibEventLoop:
        return new_event_loop()

    if sys.platform != 'win32':
        def get_child_watcher(self) -> asyncio.AbstractChildWatcher:
            raise NotImplementedError

        def set_child_watcher(self, watcher: asyncio.AbstractChildWatcher) -> None:
            raise NotImplementedError
