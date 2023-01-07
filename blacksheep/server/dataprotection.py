import os
import secrets
import string
from typing import List, Optional, Sequence

from itsdangerous import Serializer
from itsdangerous.url_safe import URLSafeSerializer

from blacksheep.baseapp import get_logger

logger = get_logger()


def generate_secret(length: int = 60) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for i in range(length))


def get_keys() -> List[str]:
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
    secret_keys: Optional[Sequence[str]] = None, purpose: str = "dataprotection"
) -> Serializer:
    if not secret_keys:
        secret_keys = get_keys()
    return URLSafeSerializer(list(secret_keys), salt=purpose.encode())
