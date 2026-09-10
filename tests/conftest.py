"""Shared test fixtures."""

from collections.abc import AsyncGenerator, Iterator

import pytest
from nicegui.testing import User, user_simulation

import nasa_api
from ui import render_main_page

# Brings in NiceGUI's storage/marker setup; we override its `user` fixture below.
pytest_plugins = ["nicegui.testing.user_plugin"]


@pytest.fixture
async def user() -> AsyncGenerator[User, None]:
    """A simulated browser session on the search page.

    Mounts `render_main_page` directly rather than running `app.py`, so the app's
    `__main__` block stays free of test-only guards.
    """
    async with user_simulation(root=render_main_page) as simulated_user:
        yield simulated_user


@pytest.fixture(autouse=True)
def clear_search_cache() -> Iterator[None]:
    """Keep each test's searches independent of the ones that ran before it."""
    nasa_api.clear_cache()
    yield
    nasa_api.clear_cache()
