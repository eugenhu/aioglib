import importlib
import pytest
import sys
from typing import Any
import unittest.mock

default_reload = 'aioglib'


def pytest_runtest_setup(item: pytest.Item):
    private = Private()
    private.install(item)

    patched_modules = []
    patcher_recipes = []

    for mark in item.iter_markers(name='patch'):
        target = None

        if mark.args:
            target = mark.args[0]
        else:
            try:
                target = mark.kwargs['target']
            except KeyError:
                raise ValueError(
                    "No patching target specified"
                )

        target_parts = target.split('.')
        module_part = '.'.join(target_parts[:-1])

        patched_modules.append(module_part)
        patcher_recipes.append((mark.args, mark.kwargs))

    for recipe in patcher_recipes:
        patcher = unittest.mock.patch(*recipe[0], **recipe[1])
        private.loaded_patchers.append(patcher)
        patcher.start()

    for cached_module in tuple(sys.modules.keys()):
        if cached_module in patched_modules:
            continue

        if not cached_module.startswith(default_reload):
            continue

        private.reloaded_modules.append(cached_module)
        importlib.reload(sys.modules[cached_module])


def pytest_runtest_teardown(item: pytest.Item):
    private = Private.get(item)

    for patcher in private.loaded_patchers:
        patcher.stop()

    for module_name in private.reloaded_modules:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])


class Private:
    _secret_key = '_patch_private_data'

    def __init__(self):
        self.reloaded_modules = []
        self.loaded_patchers = []

    def install(self, target: Any) -> None:
        target.__dict__[__class__._secret_key] = self

    @staticmethod
    def get(owner: Any) -> 'Private':
        return owner.__dict__[__class__._secret_key]
