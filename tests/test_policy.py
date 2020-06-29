from pytest import fixture, mark, raises
from unittest.mock import Mock, call
from gi.repository import GLib
from concurrent.futures import ThreadPoolExecutor

from aioglib import GLibEventLoopPolicy


@fixture
def policy():
    # Re-import in case module was reloaded after patching.
    from aioglib._policy import GLibEventLoopPolicy
    return GLibEventLoopPolicy()


@mark.patch('aioglib._policy.get_event_loop')
def test_policy_get_event_loop(policy: GLibEventLoopPolicy):
    from aioglib._policy import get_event_loop as f

    assert policy.get_event_loop() == f.return_value
    assert f.call_args_list == [call()]


@mark.patch('aioglib._policy.new_event_loop')
def test_policy_new_event_loop(policy: GLibEventLoopPolicy):
    from aioglib._policy import new_event_loop as f

    assert policy.new_event_loop() == f.return_value
    assert f.call_args_list == [call()]


@mark.patch('aioglib._policy.set_event_loop')
def test_policy_set_event_loop(policy: GLibEventLoopPolicy):
    from aioglib._policy import set_event_loop as f

    loop = Mock()
    policy.set_event_loop(loop)

    assert f.call_args_list == [call(loop)]


def test_get_event_loop_in_main_thread():
    from aioglib._policy import get_event_loop

    loop = get_event_loop()

    assert loop.context == GLib.MainContext.default()


def test_get_event_loop_in_other_thread_with_no_default():
    from aioglib._policy import get_event_loop

    with ThreadPoolExecutor() as threads:
        def func():
            return get_event_loop()
        loop = threads.submit(func).result()

    assert loop.context == GLib.MainContext.default()


def test_get_event_loop_in_other_thread_with_default():
    from aioglib._policy import get_event_loop

    context = GLib.MainContext()

    with ThreadPoolExecutor() as threads:
        def func():
            context.push_thread_default()
            loop = get_event_loop()
            context.pop_thread_default()
            return loop
        loop = threads.submit(func).result()

    assert loop.context == context


def test_set_event_loop():
    from aioglib._policy import set_event_loop

    with raises(RuntimeError):
        set_event_loop(Mock())


def test_get_default_loop_in_main_thread():
    from aioglib._policy import get_default_loop

    loop = get_default_loop()

    assert loop.context == GLib.MainContext.default()


def test_get_default_loop_in_other_thread_with_no_default():
    from aioglib._policy import get_default_loop

    with ThreadPoolExecutor() as threads:
        def func():
            return get_default_loop()
        loop = threads.submit(func).result()

    assert loop.context == GLib.MainContext.default()


def test_get_default_loop_in_other_thread_with_default():
    from aioglib._policy import get_default_loop

    with ThreadPoolExecutor() as threads:
        def func():
            context = GLib.MainContext()
            context.push_thread_default()
            loop = get_default_loop()
            context.pop_thread_default()
            return loop
        loop = threads.submit(func).result()

    assert loop.context == GLib.MainContext.default()


@mark.patch('aioglib._helpers.get_running_context')
def test_get_running_loop():
    from aioglib._helpers import get_running_context as mock_get_running_context
    from aioglib._policy import get_running_loop

    loop = get_running_loop()

    assert loop.context == mock_get_running_context.return_value
    assert mock_get_running_context.call_args_list == [call()]


@mark.patch('aioglib._helpers.get_running_context')
def test_get_running_loop_when_none_running():
    from aioglib._helpers import get_running_context as mock_get_running_context
    from aioglib._policy import get_running_loop

    mock_get_running_context.return_value = None

    with raises(RuntimeError):
        get_running_loop()


def test_new_event_loop():
    from aioglib import GLibEventLoop
    from aioglib._policy import new_event_loop

    loop = new_event_loop()

    assert isinstance(loop, GLibEventLoop)

    # Just make sure the new loop's context isn't the global default context I guess.
    assert loop.context != GLib.MainContext.default()
