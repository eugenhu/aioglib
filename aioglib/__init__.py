import asyncio
import sys
import threading
from typing import Optional, Any, Callable, Iterable, Mapping
import traceback
from gi.repository import GLib
import logging

try:
    import contextvars
except ImportError:
    from . import _fakecontextvars as contextvars

from . import _format_helpers

_ExceptionHandler = Callable[[asyncio.AbstractEventLoop, Mapping], Any]

logger = logging.getLogger(__package__)


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
        self._exception_handler = None  # type: Optional[_ExceptionHandler]

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

    def get_exception_handler(self) -> Optional[_ExceptionHandler]:
        return self._exception_handler

    def set_exception_handler(self, handler: Optional[_ExceptionHandler]) -> None:
        if handler is not None and not callable(handler):
            raise TypeError('A callable object or None is expected, got {!r}'.format(handler))

        self._exception_handler = handler

    def call_exception_handler(self, context: Mapping) -> None:
        if self._exception_handler is None:
            try:
                self.default_exception_handler(context)
            except (SystemExit, KeyboardInterrupt):
                raise
            except BaseException:
                # Second protection layer for unexpected errors in the default implementation.
                logger.error('Exception in default exception handler', exc_info=True)
        else:
            try:
                self._exception_handler(self, context)
            except (SystemExit, KeyboardInterrupt):
                raise
            except BaseException as exc:
                # Exception in the user set custom exception handler.
                try:
                    # Log the exception raised in the custom handler in the default handler.
                    self.default_exception_handler({
                        'message': 'Unhandled error in exception handler',
                        'exception': exc,
                        'context': context,
                    })
                except (SystemExit, KeyboardInterrupt):
                    raise
                except BaseException:
                    # Again, in case there is an unexpected error in the default implementation.
                    logger.error(
                        msg='Exception in default exception handler while handling an unexpected error in '
                            'custom exception handler',
                        exc_info=True,
                    )

    def default_exception_handler(self, context):
        message = context.get('message')
        if not message:
            message = 'Unhandled exception in event loop'

        exception = context.get('exception')
        if exception is not None:
            exc_info = (type(exception), exception, exception.__traceback__)
        else:
            exc_info = False

        log_lines = [message]
        for key in sorted(context):
            if key in {'message', 'exception'}:
                continue

            value = context[key]

            if key == 'source_traceback':
                tb = ''.join(traceback.format_list(value))
                value = 'Object created at (most recent call last):\n'
                value += tb.rstrip()
            else:
                value = repr(value)

            log_lines.append('{}: {}'.format(key, value))

        logger.error('\n'.join(log_lines), exc_info=exc_info)

    def call_soon(self, callback, *args, context=None) -> 'GLibSourceHandle':
        if self._debug:
            self._check_callback(callback, 'call_soon')
            frame = sys._getframe(1)
        else:
            frame = None

        return self._idle_add(callback, args, context, frame)

    def call_soon_threadsafe(self, callback, *args, context=None) -> 'GLibSourceHandle':
        if self._debug:
            self._check_callback(callback, 'call_soon_threadsafe')
            frame = sys._getframe(1)
        else:
            frame = None

        # Adding and removing sources to contexts is thread-safe.
        return self._idle_add(callback, args, context, frame)

    def _idle_add(self, callback, args, context=None, frame=None) -> 'GLibSourceHandle':
        source = GLib.Idle()
        return self._attach_source_with_callback(source, callback, args, context, frame)

    def call_later(self, delay, callback, *args, context=None):
        if self._debug:
            self._check_callback(callback, 'call_later')
            frame = sys._getframe(1)
        else:
            frame = None

        return self._timeout_add(delay, callback, args, context, frame)

    def call_at(self, when, callback, *args, context=None):
        if self._debug:
            self._check_callback(callback, 'call_at')
            frame = sys._getframe(1)
        else:
            frame = None

        delay = when - self.time()

        return self._timeout_add(delay, callback, args, context, frame)

    def _timeout_add(self, delay, callback, args, context=None, frame=None) -> 'GLibSourceHandle':
        # GLib.Timeout expects milliseconds.
        source = GLib.Timeout(delay * 1000)
        return self._attach_source_with_callback(source, callback, args, context, frame)

    def _attach_source_with_callback(
            self,
            source,
            callback,
            args,
            context=None,
            frame=None,
    ) -> 'GLibSourceHandle':
        source_name = _format_helpers.format_callback_source(callback, args)

        if frame is not None:
            traceback = _format_helpers.extract_stack(frame)
            source_name += ' created at {f.filename}:{f.lineno}'.format(f=frame)
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

    def _check_callback(self, callback: Any, method: str) -> None:
        if (asyncio.iscoroutine(callback) or asyncio.iscoroutinefunction(callback)):
            raise TypeError("coroutines cannot be used with {method}()".format(method=method))
        if not callable(callback):
            raise TypeError(
                "a callable object was expected by {method}(), got {callback!r}"
                .format(method=method, callback=callback)
            )

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
    """Wrapper that calls an exception handler if an exception occurs during callback invocation. If a context
    is not provided, the wrapped callback will be called with a copy of the current context."""

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
            exception_handler: Callable[[Mapping], Any],
            traceback: Optional[traceback.StackSummary] = None,
            context: Optional[contextvars.Context] = None,
    ) -> None:
        self._callback = callback
        self._args = args
        self._exception_handler = exception_handler
        self._traceback = traceback
        self._context = context if context is not None else contextvars.copy_context()
        self._handle = None  # type: Optional[GLibSourceHandle]

    def set_handle(self, handle: 'GLibSourceHandle') -> None:
        self._handle = handle

    def __call__(self) -> bool:
        try:
            self._context.run(self._callback, *self._args)
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

        when = self.when()
        if when >= 0:
            info.append('when={}'.format(when))

        info.append(self._source.get_name())

        return '<{}>'.format(' '.join(info))

    def cancel(self):
        if self._source.is_destroyed(): return
        self._source.destroy()

    def cancelled(self):
        return self._source.is_destroyed()

    def when(self) -> float:
        return self._source.get_ready_time()/1e6
