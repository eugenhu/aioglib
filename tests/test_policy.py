import gc
import weakref
from pytest import fixture, raises
from gi.repository import GLib
from aioglib import GLibEventLoopPolicy


@fixture
def policy() -> GLibEventLoopPolicy:
    from aioglib._policy import GLibEventLoopPolicy
    return GLibEventLoopPolicy()


def test_policy_get_event_loop(policy: GLibEventLoopPolicy):
    loop = policy.get_event_loop()

    assert loop.context == GLib.MainContext.default()


def test_policy_get_event_loop_with_default_set(policy: GLibEventLoopPolicy):
    context = GLib.MainContext()
    context.push_thread_default()

    loop = policy.get_event_loop()

    assert loop.context == context


def test_policy_new_event_loop(policy: GLibEventLoopPolicy):
    current_loop = policy.get_event_loop()
    new_loop = policy.new_event_loop()

    assert new_loop is not current_loop
    assert new_loop.context == current_loop.context


def test_policy_new_event_loop_with_default_set(policy: GLibEventLoopPolicy):
    context = GLib.MainContext()
    context.push_thread_default()

    new_loop = policy.new_event_loop()

    assert new_loop.context == context


def test_policy_set_event_loop(policy: GLibEventLoopPolicy):
    from aioglib import GLibEventLoop

    old_loop = policy.get_event_loop()
    new_loop = policy.new_event_loop()

    policy.set_event_loop(new_loop)

    assert policy.get_event_loop() is new_loop


def test_policy_set_event_loop_with_wrong_context(policy: GLibEventLoopPolicy):
    from aioglib import GLibEventLoop

    new_context = GLib.MainContext()
    bad_loop = GLibEventLoop(new_context)

    with raises(ValueError):
        policy.set_event_loop(bad_loop)


def test_policy_get_event_loop_persists(policy: GLibEventLoopPolicy):
    loop = policy.get_event_loop()
    
    # Mark this instance.
    loop._secret = 'something'

    del loop
    gc.collect()

    loop = policy.get_event_loop()

    assert loop._secret == 'something'


def test_policy_set_event_loop_persists(policy: GLibEventLoopPolicy):
    loop = policy.new_event_loop()

    # Mark this instance.
    loop._secret = 'something'
    policy.set_event_loop(loop)

    del loop
    gc.collect()

    loop = policy.get_event_loop()

    assert loop._secret == 'something'


def test_policy_does_not_hold_refs_to_old_loops(policy: GLibEventLoopPolicy):
    old_loop = policy.get_event_loop()
    new_loop = policy.new_event_loop()

    policy.set_event_loop(new_loop)

    old_loop_wr = weakref.ref(old_loop)
    del old_loop
    gc.collect()

    assert old_loop_wr() is None
