import os
from unittest.mock import patch

import pytest

from blacksheep.server.env import EnvironmentSettings


def test_env_settings():
    with patch.dict(os.environ, {"APP_SHOW_ERROR_DETAILS": "1"}):
        env = EnvironmentSettings.from_env()
        assert env.show_error_details is True

    with patch.dict(os.environ, {"APP_SHOW_ERROR_DETAILS": "0"}):
        env = EnvironmentSettings.from_env()
        assert env.show_error_details is False

    with patch.dict(os.environ, {"APP_SHOW_ERROR_DETAILS": "true"}):
        env = EnvironmentSettings.from_env()
        assert env.show_error_details is True


def test_env_settings_env_property():
    with patch.dict(os.environ, {"APP_ENV": "development"}):
        env = EnvironmentSettings.from_env()
        assert env.env == "development"

    with patch.dict(os.environ, {"APP_ENV": "production"}):
        env = EnvironmentSettings.from_env()
        assert env.env == "production"


def test_env_settings_default_env():
    with patch.dict(os.environ, {}, clear=True):
        env = EnvironmentSettings.from_env()
        assert env.env == "production"


def test_env_settings_mount_auto_events():
    with patch.dict(os.environ, {"APP_MOUNT_AUTO_EVENTS": "1"}):
        env = EnvironmentSettings.from_env()
        assert env.mount_auto_events is True

    with patch.dict(os.environ, {"APP_MOUNT_AUTO_EVENTS": "0"}):
        env = EnvironmentSettings.from_env()
        assert env.mount_auto_events is False

    with patch.dict(os.environ, {"APP_MOUNT_AUTO_EVENTS": "false"}):
        env = EnvironmentSettings.from_env()
        assert env.mount_auto_events is False


def test_env_settings_mount_auto_events_default():
    with patch.dict(os.environ, {}, clear=True):
        env = EnvironmentSettings.from_env()
        assert env.mount_auto_events is True


def test_env_settings_use_default_router():
    with patch.dict(os.environ, {"APP_DEFAULT_ROUTER": "1"}):
        env = EnvironmentSettings.from_env()
        assert env.use_default_router is True

    with patch.dict(os.environ, {"APP_DEFAULT_ROUTER": "0"}):
        env = EnvironmentSettings.from_env()
        assert env.use_default_router is False


def test_env_settings_use_default_router_default():
    with patch.dict(os.environ, {}, clear=True):
        env = EnvironmentSettings.from_env()
        assert env.use_default_router is True


def test_env_settings_add_signal_handler():
    with patch.dict(os.environ, {"APP_SIGNAL_HANDLER": "1"}):
        env = EnvironmentSettings.from_env()
        assert env.add_signal_handler is True

    with patch.dict(os.environ, {"APP_SIGNAL_HANDLER": "0"}):
        env = EnvironmentSettings.from_env()
        assert env.add_signal_handler is False


def test_env_settings_add_signal_handler_default():
    with patch.dict(os.environ, {}, clear=True):
        env = EnvironmentSettings.from_env()
        assert env.add_signal_handler is False


def test_env_settings_http_scheme():
    with patch.dict(os.environ, {"APP_HTTP_SCHEME": "http"}):
        env = EnvironmentSettings.from_env()
        assert env.http_scheme == "http"

    with patch.dict(os.environ, {"APP_HTTP_SCHEME": "https"}):
        env = EnvironmentSettings.from_env()
        assert env.http_scheme == "https"


def test_env_settings_http_scheme_default():
    with patch.dict(os.environ, {}, clear=True):
        env = EnvironmentSettings.from_env()
        assert env.http_scheme is None


def test_env_settings_force_https():
    with patch.dict(os.environ, {"APP_FORCE_HTTPS": "1"}):
        env = EnvironmentSettings.from_env()
        assert env.force_https is True

    with patch.dict(os.environ, {"APP_FORCE_HTTPS": "0"}):
        env = EnvironmentSettings.from_env()
        assert env.force_https is False

    with patch.dict(os.environ, {"APP_FORCE_HTTPS": "yes"}):
        env = EnvironmentSettings.from_env()
        assert env.force_https is True


def test_env_settings_force_https_default():
    with patch.dict(os.environ, {}, clear=True):
        env = EnvironmentSettings.from_env()
        assert env.force_https is False


def test_env_settings_constructor():
    env = EnvironmentSettings(
        env="test",
        show_error_details=True,
        mount_auto_events=False,
        use_default_router=False,
        add_signal_handler=True,
        http_scheme="https",
        force_https=True,
    )
    assert env.env == "test"
    assert env.show_error_details is True
    assert env.mount_auto_events is False
    assert env.use_default_router is False
    assert env.add_signal_handler is True
    assert env.http_scheme == "https"
    assert env.force_https is True


def test_env_settings_constructor_defaults():
    env = EnvironmentSettings()
    assert env.env == "local"
    assert env.show_error_details is False
    assert env.mount_auto_events is True
    assert env.use_default_router is True
    assert env.add_signal_handler is False
    assert env.http_scheme is None
    assert env.force_https is False


def test_env_settings_invalid_http_scheme():
    with pytest.raises(ValueError, match="Invalid http_scheme"):
        EnvironmentSettings(http_scheme="ftp")

    with pytest.raises(ValueError, match="Invalid http_scheme"):
        EnvironmentSettings(http_scheme="invalid")
