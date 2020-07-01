import asyncio
from gi.repository import GLib
import threading
from typing import Optional, MutableMapping, NoReturn
import sys
import weakref

from ._loop import GLibEventLoop

__all__ = [
    'GLibEventLoopPolicy',
]


class GLibEventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    class _ThreadLocalVariable(threading.local):
        value = None

    def __init__(self) -> None:
        self._set_loops_lock = threading.Lock()
        self._set_loops = weakref.WeakValueDictionary()  # type: MutableMapping[GLib.MainContext, GLibEventLoop]
        self._last_accessed_loop = __class__._ThreadLocalVariable()

    def get_event_loop(self) -> GLibEventLoop:
        context = self._get_current_context()
        if context is None:
            self._raise_no_context()

        with self._set_loops_lock:
            try:
                loop = self._set_loops[context]
            except KeyError:
                loop = GLibEventLoop(context)
                self._set_loops[context] = loop

        self._last_accessed_loop.value = loop

        return loop

    def set_event_loop(self, loop: GLibEventLoop) -> None:
        context = self._get_current_context()
        if context is None:
            self._raise_no_context()

        if loop.context != context:
            raise ValueError("Loop has a different context")

        with self._set_loops_lock:
            self._set_loops[context] = loop

        self._last_accessed_loop.value = loop

    def new_event_loop(self) -> GLibEventLoop:
        context = self._get_current_context()
        if context is None:
            self._raise_no_context()

        return GLibEventLoop(context)

    def _get_current_context(self) -> Optional[GLib.MainContext]:
        if threading.current_thread() is threading.main_thread():
            context = GLib.MainContext.default()
        else:
            context = GLib.MainContext.get_thread_default()  # This could be None.

        return context

    def _raise_no_context(self) -> NoReturn:
        raise RuntimeError(
            "No default context set for this thread ({})"
            .format(threading.current_thread().name)
        )

    if sys.platform != 'win32':
        def get_child_watcher(self) -> asyncio.AbstractChildWatcher:
            raise NotImplementedError

        def set_child_watcher(self, watcher: asyncio.AbstractChildWatcher) -> None:
            raise NotImplementedError
