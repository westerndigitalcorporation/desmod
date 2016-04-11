import pytest
import simpy


@pytest.fixture
def env():
    """Fixture providing simpy.Environment for tests with `env` argument."""
    return simpy.Environment()
