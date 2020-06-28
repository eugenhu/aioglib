import asyncio
import sys
import threading
from typing import Optional, Any, Callable, Iterable
import traceback
from gi.repository import GLib

try:
    import contextvars
except ImportError:
    from . import _fakecontextvars as contextvars

from . import _format_helpers


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
    loop = _get_running_loop()
    if loop is None:
        raise RuntimeError('no running event loop')

    return loop

def _get_running_loop() -> Optional['GLibEventLoop']:
    current_source = GLib.main_current_source()
    if current_source is None:
        return None

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

    def run_forever(self):
        self._check_running()
        self._check_is_owner()

        old_running_loop = asyncio._get_running_loop()

        try:
            self._mainloop = GLib.MainLoop(self._context)
            asyncio._set_running_loop(self)
            self._mainloop.run()
        finally:
            self._mainloop = None
            asyncio._set_running_loop(old_running_loop)

    def run_until_complete(self, future: asyncio.Future) -> Any:
        self._check_running()
        self._check_is_owner()

        new_task = not asyncio.isfuture(future)
        future = asyncio.ensure_future(future, loop=self)
        if new_task:
            # An exception is raised if the future didn't complete, so there is no need to log the "destroy
            # pending task" message
            future._log_destroy_pending = False

        future.add_done_callback(_run_until_complete_cb)
        try:
            self.run_forever()
        except:
            if new_task and future.done() and not future.cancelled():
                # The coroutine raised a BaseException. Consume the exception to not log a warning, the caller
                # doesn't have access to the local task.
                future.exception()
            raise
        finally:
            future.remove_done_callback(_run_until_complete_cb)
        if not future.done():
            raise RuntimeError('Event loop stopped before Future completed.')

        return future.result()

    def _check_running(self) -> None:
        if self.is_running():
            raise RuntimeError('This event loop is already running')

    def _check_is_owner(self) -> None:
        if not self._context.is_owner():
            raise RuntimeError(
                "The current thread ({}) is not the owner of this loop's context ({})"
                .format(threading.current_thread().name, self._context)
            )

    def stop(self):
        if self._mainloop is None:
            return

        self._mainloop.quit()

    def is_running(self) -> bool:
        running_loop = _get_running_loop()
        if running_loop is None:
            return False

        return running_loop._context == self._context

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

    def call_soon(self, callback, *args, context=None) -> 'GLibSourceHandle':
        source = GLib.Idle()
        source_name = _format_helpers.format_callback_source(callback, args)

        if self._debug:
            outer_frame = sys._getframe(1)
            traceback = _format_helpers.extract_stack(outer_frame)

            source_name += ' created at {f.filename}:{f.lineno}'.format(f=outer_frame)
        else:
            traceback = None

        source.set_name(source_name)

        callback_wrapper = _CallbackWrapper(
            callback=callback,
            args=args,
            exception_handler=self.call_exception_handler,
            traceback=traceback,
            context=context,
        )
        source.set_callback(callback_wrapper)

        handle = GLibSourceHandle(source)
        callback_wrapper.set_handle(handle)

        return handle

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

    _debug = False

    def set_debug(self, enabled: bool) -> None:
        self._debug = enabled

    def get_debug(self) -> bool:
        return self._debug


def _run_until_complete_cb(fut):
    if not fut.cancelled():
        exc = fut.exception()
        if isinstance(exc, (SystemExit, KeyboardInterrupt)):
            # Issue #22429: run_forever() already finished, no need to stop it.
            return

    try:
        # Future.get_loop() was added in Python 3.7.
        fut.get_loop().stop()
    except AttributeError:
        pass
    else:
        # Access private '_loop' attribute as fallback.
        fut._loop.stop()


class _CallbackWrapper:
    """Wrapper that calls an exception handler if an exception occurs during callback invocation."""

    __slots__ = (
        '_callback',
        '_args',
        '_exception_handler',
        '_traceback',
        '_context',
        '_handle',
        '__weakref__'
    )

    def __init__(
            self,
            callback: Callable,
            args: Iterable,
            exception_handler: Callable,
            traceback: Optional[traceback.StackSummary] = None,
            context: Optional[contextvars.Context] = None,
    ) -> None:
        self._callback = callback
        self._args = args
        self._exception_handler = exception_handler
        self._traceback = traceback
        self._context = context
        self._handle = None  # type: Optional[Handle]

    def set_handle(self, handle: 'Handle') -> None:
        self._handle = handle

    def __call__(self) -> bool:
        try:
            if self._context is not None:
                self._context.run(self._callback, *self._args)
            else:
                self._callback(*self._args)
        except (SystemExit, KeyboardInterrupt):
            # Pass through SystemExit and KeyboardInterrupt
            raise
        except BaseException as exc:
            exc_context = {}

            exc_context['exception'] = exc

            exc_context['message'] = 'Exception in callback {callback_repr}'.format(
                callback_repr=_format_helpers.format_callback_source(self._callback, self._args)
            )

            if self._handle:
                exc_context['handle'] = self._handle

            if self._traceback:
                exc_context['source_traceback'] = self._traceback

            self._exception_handler(exc_context)

        # Not sure if this is necessary, but something similar is done in asyncio.Handle.
        self = None

        # Remove this callback's source after it's been dispatched.
        return GLib.SOURCE_REMOVE


class GLibSourceHandle:
    """Object returned by callback registration methods."""

    __slots__ = ('_source', '__weakref__')

    def __init__(self, source: GLib.Source) -> None:
        self._source = source

    def __repr__(self):
        info = [__class__.__name__]

        if self.cancelled():
            info.append('cancelled')

        info.append(self._source.get_name())

        return '<{}>'.format(' '.join(info))

    def cancel(self):
        if self._source.is_destroyed(): return
        self._source.destroy()

    def cancelled(self):
        return self._source.is_destroyed()
