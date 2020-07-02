import asyncio
import math
import sys
from unittest.mock import Mock, call, patch

from gi.repository import GLib
from pytest import fixture, mark, raises

import aioglib

# Import for type annotations.
from aioglib import GLibEventLoop


class MockMainContext:
    def __init__(self, is_owner: bool = True):
        self.acquire_count = 0
        self._is_owner = is_owner

    def acquire(self):
        self.acquire_count += 1
        return self._is_owner

    def release(self):
        self.acquire_count -= 1


class MockTimeout:
    def __init__(self, interval, priority=GLib.PRIORITY_DEFAULT):
        self._interval = interval
        self._priority = priority

    def __eq__(self, other):
        if not isinstance(other, MockTimeout):
            return False

        return math.isclose(self._interval, other._interval)

    def __repr__(self):
        # For debugging.
        return '<MockTimeout interval={}>'.format(self._interval)


class MockGLibSourceHandle:
    def __init__(self, source):
        self.source = source
        print('init', source)

    def __eq__(self, other):
        if not isinstance(other, MockGLibSourceHandle):
            return False

        return self.source == other.source


class MockSource:
    def __init__(self):
        self.name = 'MockSource'
        self.callback = None
        self.data = None
        self.priority = GLib.PRIORITY_DEFAULT
        self.context = None

        self._ready_time = -1
        self._is_destroyed = False

    def set_name(self, name):
        self.name = name

    def get_name(self):
        return self.name

    def set_callback(self, callback, data=None):
        self.callback = callback
        self.data = data

    def set_priority(self, priority):
        self.priority = priority

    def attach(self, context):
        self.context = context
    
    def set_ready_time(self, time):
        self._ready_time = time
    
    def get_ready_time(self):
        return self._ready_time

    def destroy(self):
        self._is_destroyed = True

    def is_destroyed(self):
        return self._is_destroyed


@fixture
def loop():
    from aioglib._loop import GLibEventLoop
    return GLibEventLoop(GLib.MainContext())


def idle_add(context: GLib.MainContext, callback) -> GLib.Source:
    source = GLib.Idle()
    source.set_callback(lambda data: callback())
    source.attach(context)

    return source


@mark.patch("gi.repository.GLib.MainLoop")
def test_loop_init():
    from aioglib._loop import GLibEventLoop

    context = Mock()
    loop = GLibEventLoop(context)

    assert loop.context == context


@mark.timeout(1, method='thread')
def test_loop_run_forever_and_stop(loop: GLibEventLoop):
    running_loop_check = True
    always_running_check = True

    num = 10
    def countdown():
        nonlocal num, running_loop_check, always_running_check
        num -= 1

        if asyncio.get_running_loop() is not loop:
            running_loop_check = False

        always_running_check =  loop.is_running() and always_running_check

        if num > 0:
            return True
        else:
            loop.stop()
            return False

    # Iterate through context `num` times.

    context = loop.context

    source = idle_add(context, countdown)

    loop.run_forever()

    assert running_loop_check
    assert always_running_check
    
    assert source.is_destroyed()
    assert not context.pending()


def test_loop_run_until_complete(loop: GLibEventLoop):
    future = asyncio.Future(loop=loop)
    running_loop_check = True
    always_running_check = True


    num = 10
    def countdown():
        nonlocal num, running_loop_check, always_running_check
        num -= 1

        if asyncio.get_running_loop() is not loop:
            running_loop_check = False

        always_running_check =  loop.is_running() and always_running_check

        if num == 0:
            future.set_result('something')

        return True
    
    context = loop.context

    source = idle_add(context, countdown)

    result = loop.run_until_complete(future)

    assert running_loop_check
    assert always_running_check

    assert result == 'something'
    assert not source.is_destroyed()


def test_loop_run_until_complete_exception(loop: GLibEventLoop):
    future = asyncio.Future(loop=loop)

    class MyException(Exception):
        pass

    idle_add(loop.context, lambda: future.set_exception(MyException('my message')))

    with raises(MyException, match='my message'):
        loop.run_until_complete(future)


def test_loop_run_until_complete_with_coro(loop: GLibEventLoop):
    async def coro():
        return 'something'

    result = loop.run_until_complete(coro())

    assert result == 'something'


def test_loop_run_until_complete_with_awaitable(loop: GLibEventLoop):
    class MyAwaitable:
        def __await__(self):
            return self
        
        def __iter__(self):
            return self
        
        def __next__(self):
            raise StopIteration('something')

    result = loop.run_until_complete(MyAwaitable())

    assert result == 'something'


def test_loop_run_until_complete_with_future_on_another_loop(loop: GLibEventLoop):
    future = asyncio.Future(loop=Mock())

    with raises(ValueError):
        loop.run_until_complete(future)


def test_loop_run_until_complete_early_stop(loop: GLibEventLoop):
    future = asyncio.Future(loop=loop)

    idle_add(loop.context, loop.stop)

    with raises(RuntimeError):
        loop.run_until_complete(future)


def test_loop_run_forever_when_already_running(loop: GLibEventLoop):
    async def main():
        loop.run_forever()

    with raises(RuntimeError):
        loop.run_until_complete(main())


def test_loop_run_until_complete_when_already_running(loop: GLibEventLoop):
    async def main():
        future = asyncio.Future(loop=loop)
        loop.run_until_complete(future)
    
    with raises(RuntimeError):
        loop.run_until_complete(main())


@mark.patch("gi.repository.GLib.MainLoop")
def test_loop_run_forever_when_not_owner():
    from aioglib._loop import GLibEventLoop

    context = MockMainContext(is_owner=False)
    loop = GLibEventLoop(context)

    with raises(RuntimeError):
        loop.run_forever()


@mark.patch("gi.repository.GLib.MainLoop")
def test_loop_run_until_complete_when_not_owner(loop: GLibEventLoop):
    from aioglib._loop import GLibEventLoop

    context = MockMainContext(is_owner=False)
    loop = GLibEventLoop(context)

    with raises(RuntimeError):
        future = asyncio.Future(loop=loop)
        loop.run_until_complete(future)


@mark.patch("gi.repository.GLib.MainLoop")
def test_loop_run_forever_releases_context():
    from gi.repository.GLib import MainLoop as MockMainLoop

    mock_context = MockMainContext()
    loop = GLibEventLoop(mock_context)

    MockMainLoop().run.side_effect = loop.stop
    MockMainLoop().is_running.return_value = False

    loop.run_forever()

    assert mock_context.acquire_count == 0


@mark.patch("gi.repository.GLib.MainLoop")
@mark.patch("gi.repository.GLib.Idle")
def test_loop_run_until_complete_releases_context():
    from gi.repository.GLib import MainLoop as MockMainLoop
    from aioglib._loop import GLibEventLoop

    mock_context = MockMainContext()
    loop = GLibEventLoop(mock_context)

    future = asyncio.Future(loop=loop)

    MockMainLoop().run.side_effect = lambda: future.set_result(None)
    MockMainLoop().is_running.return_value = False

    loop.run_until_complete(future)

    assert mock_context.acquire_count == 0


def test_loop_set_is_running(loop: GLibEventLoop):
    assert not loop.is_running()

    loop.set_is_running(True)
    assert asyncio.get_running_loop() is loop
    
    assert loop.is_running()


def test_loop_set_is_not_running(loop: GLibEventLoop):
    old_loop = Mock()
    asyncio._set_running_loop(old_loop)

    loop.set_is_running(True)
    loop.set_is_running(False)
    assert not loop.is_running()

    assert asyncio.get_running_loop() is old_loop


@mark.patch("gi.repository.GLib.MainLoop")
def test_loop_set_is_running_acquires_context():
    from gi.repository.GLib import MainLoop as MockMainLoop
    from aioglib._loop import GLibEventLoop

    mock_context = MockMainContext()
    loop = GLibEventLoop(mock_context)

    MockMainLoop().is_running.return_value = False

    loop.set_is_running(True)

    assert mock_context.acquire_count > 0


@mark.patch("gi.repository.GLib.MainLoop")
def test_loop_set_is_not_running_releases_context():
    from gi.repository.GLib import MainLoop as MockMainLoop
    from aioglib._loop import GLibEventLoop

    mock_context = MockMainContext()
    loop = GLibEventLoop(mock_context)

    MockMainLoop().is_running.return_value = False

    loop.set_is_running(True)
    loop.set_is_running(False)

    assert mock_context.acquire_count == 0


def test_loop_set_is_running_when_already_running(loop: GLibEventLoop):
    async def main():
        loop.set_is_running(True)

    with raises(RuntimeError):
        loop.run_until_complete(main())


def test_loop_run_forever_when_set_is_running(loop: GLibEventLoop):
    loop.set_is_running(True)

    with raises(RuntimeError):
        loop.run_forever()


def test_loop_run_until_complete_when_set_is_running(loop: GLibEventLoop):
    loop.set_is_running(True)

    future = asyncio.Future(loop=loop)

    with raises(RuntimeError):
        loop.run_until_complete(future)


@mark.patch('gi.repository.GLib.MainLoop')
def test_loop_set_is_running_when_not_owner():
    from aioglib._loop import GLibEventLoop

    context = MockMainContext(is_owner=False)
    loop = GLibEventLoop(context)

    with raises(RuntimeError):
        loop.set_is_running(True)


def test_loop_set_is_not_running_when_started_with_run(loop: GLibEventLoop):
    async def main():
        loop.set_is_running(False)

    with raises(RuntimeError):
        loop.run_until_complete(main())


def test_loop_set_is_not_running_is_idempotent(loop: GLibEventLoop):
    old_loop = Mock()
    asyncio._set_running_loop(old_loop)

    loop.set_is_running(False)
    loop.set_is_running(False)

    assert asyncio.get_running_loop() is old_loop

    loop.set_is_running(True)
    loop.set_is_running(False)
    loop.set_is_running(False)

    assert asyncio.get_running_loop() is old_loop


def test_loop_run_forever_after_toggle_set_is_running(loop: GLibEventLoop):
    loop.set_is_running(True)
    loop.set_is_running(False)

    idle_add(loop.context, loop.stop)

    loop.run_forever()


def test_loop_is_closed(loop: GLibEventLoop):
    assert not loop.is_closed()


def test_loop_close(loop: GLibEventLoop):
    with raises(RuntimeError):
        loop.close()


@mark.patch('gi.repository.GLib.Idle')
@mark.parametrize('method', ['call_soon', 'call_soon_threadsafe'])
@mark.parametrize('with_debug', [False, True])
def test_loop_call_soon(loop: GLibEventLoop, method: str, with_debug: bool):
    from gi.repository.GLib import Idle as MockIdle

    if with_debug:
        loop.set_debug(True)

    with patch.object(loop, '_schedule_callback', autospec=True) as mock_schedule_callback:
        callback = Mock()
        arg1, arg2, arg3 = Mock(), Mock(), Mock()
        callback_context = Mock()
        frame = sys._getframe() if with_debug else None

        handle = getattr(loop, method)(callback, arg1, arg2, arg3, context=callback_context)

        assert handle is loop._schedule_callback.return_value

        mock_schedule_callback.assert_called_once_with(
            source=MockIdle(),
            callback=callback,
            args=(arg1, arg2, arg3),
            callback_context=callback_context,
            frame=frame,
        )


@mark.patch('gi.repository.GLib.Timeout', new=MockTimeout)
@mark.parametrize('with_debug', [False, True])
def test_loop_call_later(loop: GLibEventLoop, with_debug: bool):
    if with_debug:
        loop.set_debug(True)

    with patch.object(loop, '_schedule_callback', autospec=True) as mock_schedule_callback:
        callback = Mock()
        arg1, arg2, arg3 = Mock(), Mock(), Mock()
        callback_context = Mock()
        frame = sys._getframe() if with_debug else None

        # Delay is specified in seconds.
        handle = loop.call_later(123, callback, arg1, arg2, arg3, context=callback_context)

        assert handle is loop._schedule_callback.return_value

        mock_schedule_callback.assert_called_once_with(
            source=MockTimeout(123*1000),  # GLib.Timeout expects milliseconds.
            callback=callback,
            args=(arg1, arg2, arg3),
            callback_context=callback_context,
            frame=frame,
        )


@mark.patch('gi.repository.GLib.Timeout', new=MockTimeout)
@mark.patch('gi.repository.GLib.get_monotonic_time')
@mark.parametrize('with_debug', [False, True])
def test_loop_call_at(loop: GLibEventLoop, with_debug: bool):
    from gi.repository.GLib import get_monotonic_time as mock_get_monotonic_time

    # Fix a time (in microseconds).
    frozen_time = 314159265

    # Make GLib.mock_get_monotonic_time() return a constant time for this test.
    mock_get_monotonic_time.return_value = frozen_time

    if with_debug:
        loop.set_debug(True)

    with patch.object(loop, '_schedule_callback', autospec=True) as mock_schedule_callback:
        callback = Mock()
        arg1, arg2, arg3 = Mock(), Mock(), Mock()
        callback_context = Mock()
        frame = sys._getframe() if with_debug else None

        # Time is specified in seconds.
        handle = loop.call_at(123, callback, arg1, arg2, arg3, context=callback_context)

        assert handle is loop._schedule_callback.return_value

        mock_schedule_callback.assert_called_once_with(
            source=MockTimeout(123*1000 - frozen_time/1000),  # GLib.Timeout expects milliseconds.
            callback=callback,
            args=(arg1, arg2, arg3),
            callback_context=callback_context,
            frame=frame,
        )


@mark.patch('aioglib._loop.GLibSourceHandle', new=MockGLibSourceHandle)
def test_loop_schedule_callback(loop: GLibEventLoop):
    source = MockSource()
    callback = Mock()
    arg1 = Mock()
    arg2 = Mock()
    arg3 = Mock()
    callback_context = Mock()
    frame = sys._getframe()

    handle = loop._schedule_callback(source, callback, (arg1, arg2, arg3), callback_context, frame)

    assert handle == MockGLibSourceHandle(source)

    assert source.context == loop.context

    assert callback.not_called
    assert callback_context.run.not_called

    # Emulate dispatch.
    source.callback(source.data)

    assert callback_context.run.call_args_list == [call(callback, arg1, arg2, arg3)]


@mark.patch('aioglib._loop.contextvars')
def test_loop_schedule_callback_without_context(loop: GLibEventLoop):
    from aioglib._loop import contextvars as mock_contextvars

    mock_context = Mock()
    mock_contextvars.copy_context.return_value = mock_context

    source = MockSource()
    callback = Mock()
    arg1 = Mock()
    arg2 = Mock()
    arg3 = Mock()
    callback_context = None
    frame = None

    loop._schedule_callback(source, callback, (arg1, arg2, arg3), callback_context, frame)

    # Emulate dispatch.
    source.callback(source.data)

    assert mock_context.run.call_args_list == [call(callback, arg1, arg2, arg3)]


def test_loop_create_future(loop: GLibEventLoop):
    future = loop.create_future()

    assert asyncio.isfuture(future)
    
    try:
        # Future.get_loop() was added in Python 3.7.
        future_loop = future.get_loop()
    except AttributeError:
        # Otherwise skip Future's loop check.
        future_loop = None

    if future_loop:
        assert future_loop == loop


def test_loop_create_task(loop: GLibEventLoop):
    async def main():
        return 123
    
    task = loop.create_task(main())

    result = loop.run_until_complete(task)

    assert result == 123


def test_loop_get_set_task_factory(loop: GLibEventLoop):
    task_factory = Mock()

    loop.set_task_factory(task_factory)

    assert loop.get_task_factory() == task_factory


def test_loop_create_task_with_custom_task_factory(loop: GLibEventLoop):
    task_factory = Mock()
    loop.set_task_factory(task_factory)

    mock_coro = Mock()
    task = loop.create_task(mock_coro)

    assert task == task_factory.return_value
    assert task_factory.call_args_list == [call(loop, mock_coro)]


def test_loop_get_set_debug(loop: GLibEventLoop):
    loop.set_debug(True)
    assert loop.get_debug() is True
    assert sys.get_coroutine_origin_tracking_depth() == aioglib.constants.DEBUG_STACK_DEPTH

    loop.set_debug(False)
    assert loop.get_debug() is False


def test_loop_get_set_debug_restores_coroutine_origin_tracking_depth(loop: GLibEventLoop):
    sys.set_coroutine_origin_tracking_depth(123)

    loop.set_debug(True)
    loop.set_debug(False)

    assert sys.get_coroutine_origin_tracking_depth() == 123


def test_loop_get_set_exception_handler(loop: GLibEventLoop):
    exception_handler = Mock()

    assert loop.get_exception_handler() is None

    loop.set_exception_handler(exception_handler)

    assert loop.get_exception_handler() is exception_handler

    loop.set_exception_handler(None)

    assert loop.get_exception_handler() is None


def test_loop_call_exception_handler_with_custom_exception_handler(loop: GLibEventLoop):
    exception_handler = Mock()
    loop.set_exception_handler(exception_handler)

    mock_exception_context = Mock()
    loop.call_exception_handler(mock_exception_context)

    assert exception_handler.call_args_list == [call(loop, mock_exception_context)]


@mark.patch('gi.repository.GLib.get_monotonic_time')
def test_loop_time(loop: GLibEventLoop):
    from gi.repository.GLib import get_monotonic_time as mock_get_monotonic_time

    # GLib.get_monotonic_time() returns time in milliseconds.
    mock_get_monotonic_time.return_value = 314159265

    assert math.isclose(loop.time(), 314159265/1e6)


def test_handle_cancelled():
    from aioglib._loop import GLibSourceHandle

    source = MockSource()
    handle = GLibSourceHandle(source)
    assert not handle.cancelled()

    source.destroy()

    assert handle.cancelled()


def test_handle_cancel():
    from aioglib._loop import GLibSourceHandle

    source = MockSource()
    handle = GLibSourceHandle(source)

    handle.cancel()

    assert source.is_destroyed()


def test_handle_when():
    from aioglib._loop import GLibSourceHandle

    source = MockSource()
    handle = GLibSourceHandle(source)

    # Ready time should be in microseconds (same units as GLib.get_monotonic_time())
    source.set_ready_time(314159265)

    assert math.isclose(handle.when(), 314159265/1e6)
