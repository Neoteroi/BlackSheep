from typing import Union

from cryptography.fernet import Fernet

from . import Encryptor


class FernetEncryptor(Encryptor):
    def __init__(self, secret_key: Union[str, bytes]) -> None:
        self._fernet = Fernet(secret_key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()
