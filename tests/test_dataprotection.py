import os
from unittest.mock import patch

import pytest
from essentials.secrets import Secret
from itsdangerous import BadSignature

from blacksheep.server.dataprotection import generate_secret, get_keys, get_serializer


def get_secrets() -> list[Secret]:
    """
    Retrieve application secret keys as Secret objects.

    This is a wrapper around get_keys() that converts plain text secret strings
    into Secret objects from the essentials.secrets module for enhanced security.

    Returns:
        list[Secret]: A list of Secret objects containing the application's secret keys.

    See Also:
        get_keys(): The underlying function that retrieves or generates the keys.
    """
    return [Secret.from_plain_text(value) for value in get_keys()]


def test_get_keys_creates_default_keys():
    default_keys = get_keys()

    assert default_keys is not None
    assert len(default_keys) == 3

    assert default_keys != get_keys()


def test_get_keys_returns_keys_configured_as_env_variables():
    env_variables = []
    env_dict = {}
    for i in range(4):
        key = generate_secret()
        env_dict[f"APP_SECRET_{i}"] = key
        env_variables.append(key)

    with patch.dict(os.environ, env_dict, clear=False):
        assert get_keys() == env_variables
        assert get_keys() == env_variables


def test_get_serializer():
    serializer = get_serializer(get_secrets())

    data = {"id": "0000"}
    secret = serializer.dumps(data)
    assert isinstance(secret, str)

    parsed = serializer.loads(secret)
    assert data == parsed


def test_get_serializer_with_different_purpose():
    keys = get_secrets()
    serializer = get_serializer(keys)
    other_serializer = get_serializer(keys, purpose="test")

    data = {"id": "0000"}
    secret = serializer.dumps(data)

    with pytest.raises(BadSignature):
        other_serializer.loads(secret)


def test_get_serializer_with_default_keys():
    serializer = get_serializer()

    data = {"id": "0000"}
    secret = serializer.dumps(data)
    assert isinstance(secret, str)

    parsed = serializer.loads(secret)
    assert data == parsed
