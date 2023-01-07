import os

from blacksheep.server.env import EnvironmentSettings


def test_env_settings():
    os.environ["APP_SHOW_ERROR_DETAILS"] = "1"
    env = EnvironmentSettings()

    assert env.show_error_details is True

    os.environ["APP_SHOW_ERROR_DETAILS"] = "0"
    env = EnvironmentSettings()

    assert env.show_error_details is False

    os.environ["APP_SHOW_ERROR_DETAILS"] = "true"
    env = EnvironmentSettings()

    assert env.show_error_details is True
