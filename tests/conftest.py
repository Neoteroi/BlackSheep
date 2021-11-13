import pytest

from tests.utils.application import FakeApplication


@pytest.fixture
def app():
    return FakeApplication()
