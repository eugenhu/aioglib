import asyncio
import sys
import threading
from typing import Optional
from gi.repository import GLib


def get_event_loop() -> 'GLibEventLoop':
    """If called from the main thread, return a GLibEventLoop for the global default context. Otherwise,
    return a GLibEventLoop for the thread default context, if one has been set, otherwise for the global
    default context."""
    if threading.current_thread() is threading.main_thread():
        context = GLib.MainContext.default()
    else:
        context = GLib.MainContext.get_thread_default() or GLib.MainContext.default()

    return GLibEventLoop(context)

def set_event_loop(loop: 'GLibEventLoop') -> None:
    raise RuntimeError("set_event_loop() not supported")

def new_event_loop() -> 'GLibEventLoop':
    """Create a new GLib.MainContext and return a GLibEventLoop wrapping the new context."""
    context = GLib.MainContext()
    return GLibEventLoop(context)

def get_default_loop() -> 'GLibEventLoop':
    """Return a GLibEventLoop for the global default context."""
    context = GLib.MainContext.default()
    return GLibEventLoop(context)

def get_running_loop() -> 'GLibEventLoop':
    """Return a GLibEventLoop for the context of the currently dispatching GLib.Source."""
    current_source = GLib.main_current_source()
    if current_source is None:
        raise RuntimeError('no running event loop')

    context = current_source.get_context()
    return GLibEventLoop(context)


class GLibEventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    def get_event_loop(self) -> 'GLibEventLoop':
        return get_event_loop()

    def set_event_loop(self, loop: 'GLibEventLoop') -> None:
        return set_event_loop(loop)

    def new_event_loop(self) -> 'GLibEventLoop':
        return new_event_loop()

    if sys.platform != 'win32':
        def get_child_watcher(self) -> asyncio.AbstractChildWatcher:
            raise NotImplementedError

        def set_child_watcher(self, watcher: asyncio.AbstractChildWatcher) -> None:
            raise NotImplementedError


class GLibEventLoop(asyncio.AbstractEventLoop):
    def __init__(self, context: GLib.MainContext) -> None:
        self._context = context
        self._mainloop = None  # type: Optional[GLib.MainLoop]
        self._old_running_loop = None  # type: Optional[asyncio.AbstractEventLoop]

    def run_forever(self):
        if self.is_running():
            raise RuntimeError('This event loop is already running')

        try:
            self._old_running_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._old_running_loop = None

        asyncio._set_running_loop(self)

        self._mainloop = GLib.MainLoop(self._context)
        self._mainloop.run()

    def run_until_complete(self, future):
        raise NotImplementedError

    def stop(self):
        if self._mainloop is None:
            return

        self._mainloop.quit()
        self._mainloop = None

        asyncio._set_running_loop(self._old_running_loop)

    def is_running(self) -> bool:
        """Return True if MainContext associated with this GLibEventLoop is definitely in some running loop on
        the calling thread. Return False if unsure."""
        if self._mainloop is not None:
            return self._mainloop.is_running()

        # Use asyncio.get_running_loop() as a hint for what event loop is currently running.
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        # Another MainLoop might be running with the same MainContext as ours.
        if (running_loop is not self and isinstance(running_loop, GLibEventLoop)
                and running_loop._context == self._context):
            return running_loop._mainloop is not None and running_loop._mainloop.is_running()

        # Not sure if our context is in a running loop or not.
        return False

    def is_closed(self) -> bool:
        return False

    def close(self):
        raise RuntimeError("close() not supported")

    def get_exception_handler(self):
        raise NotImplementedError

    def set_exception_handler(self, handler):
        raise NotImplementedError

    def call_exception_handler(self, context):
        raise NotImplementedError

    def default_exception_handler(self, context):
        raise NotImplementedError

    def call_soon(self, callback, *args, context=None):
        raise NotImplementedError

    def call_soon_threadsafe(self, callback, *args, context=None):
        raise NotImplementedError

    def call_later(self, delay, callback, *args):
        raise NotImplementedError

    def call_at(self, when, callback, *args):
        raise NotImplementedError

    def time(self) -> float:
        return GLib.get_monotonic_time()/1e6

    def create_future(self):
        raise NotImplementedError

    def create_task(self, coro):
        raise NotImplementedError

    def get_task_factory(self):
        return None

    def set_task_factory(self, factory):
        raise NotImplementedError

    def add_reader(self, fd, callback, *args):
        raise NotImplementedError

    def remove_reader(self, fd):
        raise NotImplementedError

    def add_writer(self, fd, callback, *args):
        raise NotImplementedError

    def remove_writer(self, fd):
        raise NotImplementedError

    def add_signal_handler(self, signum, callback, *args):
        raise NotImplementedError

    def remove_signal_handler(self, signum):
        raise NotImplementedError

    # Stub implementation of debug

    _debug = False

    def set_debug(self, enabled: bool) -> None:
        self._debug = enabled

    def get_debug(self) -> bool:
        return self._debug
