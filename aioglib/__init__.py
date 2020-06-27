import asyncio
import sys
from gi.repository import GLib


def get_event_loop() -> asyncio.AbstractEventLoop:
    ...

def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    ...

def new_event_loop() -> asyncio.AbstractEventLoop:
    ...


class GLibEventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    def get_event_loop(self) -> asyncio.AbstractEventLoop:
        return get_event_loop()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        return set_event_loop(loop)

    def new_event_loop(self) -> asyncio.AbstractEventLoop:
        return new_event_loop()

    if sys.platform != 'win32':
        def get_child_watcher(self) -> asyncio.AbstractChildWatcher:
            raise NotImplementedError

        def set_child_watcher(self, watcher: asyncio.AbstractChildWatcher) -> None:
            raise NotImplementedError
