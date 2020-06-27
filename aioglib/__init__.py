import asyncio
import sys
from gi.repository import GLib


class GLibEventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    def get_event_loop(self) -> asyncio.AbstractEventLoop:
        ...

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        ...

    def new_event_loop(self) -> asyncio.AbstractEventLoop:
        ...

    if sys.platform != 'win32':
        def get_child_watcher(self) -> asyncio.AbstractChildWatcher:
            raise NotImplementedError

        def set_child_watcher(self, watcher: asyncio.AbstractChildWatcher) -> None:
            raise NotImplementedError
