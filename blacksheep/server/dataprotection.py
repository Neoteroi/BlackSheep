import os
import secrets
import warnings
from typing import Iterable, Sequence

from essentials.secrets import Secret
from itsdangerous import Serializer
from itsdangerous.url_safe import URLSafeSerializer

from blacksheep.baseapp import get_logger

logger = get_logger()


def generate_secret(length: int = 48) -> str:
    return secrets.token_urlsafe(length)


def get_keys() -> list[str]:
    """
    Retrieve or generate application secret keys for data protection.

    This function first attempts to load secret keys from environment variables.
    By default, it looks for variables prefixed with 'APP_SECRET' (e.g., APP_SECRET_1,
    APP_SECRET_2). The prefix can be customized using the BLACKSHEEP_SECRET_PREFIX
    environment variable.

    If no environment variables are found, the function generates three new random
    secrets on the fly. Note that generated secrets are not persisted and will change
    on application restart.

    Returns:
        list[str]: A list of secret keys as plain text strings. Returns keys from
                   environment variables if available, otherwise returns three newly
                   generated secrets.

    Note:
        For production use, always configure secrets via environment variables to
        ensure tokens remain valid across application restarts and when using
        multiple instances.

    Example:
        # Set secrets via environment variables
        export APP_SECRET_1="your-secret-key-1"
        export APP_SECRET_2="your-secret-key-2"

        # Or use a custom prefix
        export BLACKSHEEP_SECRET_PREFIX="MY_SECRET"
        export MY_SECRET_1="your-secret-key-1"
    """
    # if there are environmental variables with keys, use them;
    # by default this kind of env variables would be used:
    # APP_SECRET_1="***"
    # APP_SECRET_2="***"
    # APP_SECRET_3="***"
    app_secrets = []
    env_var_key_prefix = os.environ.get("BLACKSHEEP_SECRET_PREFIX", "APP_SECRET")

    for key, value in os.environ.items():
        if key.startswith(env_var_key_prefix) or key.startswith(
            env_var_key_prefix.replace("_", "")
        ):
            app_secrets.append(value)

    if app_secrets:
        return app_secrets

    # For best user experience, here new secrets are generated on the fly.
    logger.debug(
        "Generating secrets on the fly. Configure application secrets to support "
        "tokens validation across restarts and when using multiple instances of the "
        "application!"
    )

    return [generate_secret() for _ in range(3)]


def get_serializer(
    secret_keys: Sequence[str | Secret] | None = None, purpose: str = "dataprotection"
) -> Serializer[str]:
    secrets: list[str]
    if secret_keys:
        secrets = [secret.get_value() for secret in normalize_secrets(secret_keys)]
    if not secret_keys:
        # secrets obtained from env variables or generated on the fly
        secrets = get_keys()
    return URLSafeSerializer(list(secrets), salt=purpose.encode())


def issue_deprecation_warning_for_secret_str():
    warnings.warn(
        "Passing secrets as plain text strings is deprecated and will "
        "be removed in 2.5.x or 2.6.x. Use essentials.secrets.Secret instead.",
        DeprecationWarning,
        stacklevel=2,
    )


def normalize_secrets(secrets: Sequence[str | Secret]) -> Iterable[Secret]:
    """
    Normalize a sequence of secrets into Secret objects.

    Converts plain text strings to Secret objects while preserving existing
    Secret instances. Issues a deprecation warning when plain text strings
    are encountered.

    Args:
        secrets: A sequence of secrets as either plain strings or Secret objects.

    Yields:
        Secret: Normalized Secret objects.

    Raises:
        TypeError: If a secret is neither a string nor a Secret object.

    Warning:
        Passing secrets as plain text strings is deprecated and will be removed
        in a future version. Use essentials.secrets.Secret instead.
    """
    for secret in secrets:
        if isinstance(secret, str):
            issue_deprecation_warning_for_secret_str()
            yield Secret.from_plain_text(secret)
        elif isinstance(secret, Secret):
            yield secret
        else:
            raise TypeError(
                f"Expected secret to be str or Secret, got {type(secret).__name__}"
            )
