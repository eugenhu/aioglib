import asyncio
import sys
import time
from gi.repository import GLib


def get_event_loop() -> 'GLibEventLoop':
    ...

def set_event_loop(loop: 'GLibEventLoop') -> None:
    ...

def new_event_loop() -> 'GLibEventLoop':
    ...


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

    def run_forever(self):
        raise NotImplementedError

    def run_until_complete(self, future):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def is_running(self):
        raise NotImplementedError

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
        # https://www.python.org/dev/peps/pep-3156/#specifying-times
        return time.monotonic()

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
