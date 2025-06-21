from abc import ABC, abstractmethod
from functools import partial
from typing import Callable, List

try:
    import charset_normalizer
except ImportError:
    charset_normalizer = None


class Decoder(ABC):

    @abstractmethod
    def decode(self, value: bytes) -> str: ...


def _decode(value: bytes, encoding: str) -> str:
    return value.decode(encoding)


_decode_utf8 = partial(_decode, encoding="utf8")
_decode_iso88591 = partial(_decode, encoding="ISO-8859-1")


class DefaultDecoder(Decoder):

    def __init__(self) -> None:
        self._fns: List[Callable[[bytes, str], str]] = [_decode_utf8, _decode_iso88591]

    def decode(self, value: bytes, attempted_charset: str) -> str:
        for fn in self._fns:
            
        try:
            return value.decode("utf8")
        except UnicodeDecodeError:
            try:
                return value.decode("ISO-8859-1")
            except UnicodeDecodeError:
                if charset_normalizer is not None:
                    return value.decode(charset_normalizer.detect(value)["encoding"])  # type: ignore
                raise


class EncodingsSettings:

    def __init__(self) -> None:
        self._decoder = DefaultDecoder()

    def use(self, decoder: Decoder) -> None:
        self._decoder = decoder

    def decode(self, value: bytes):
        return self._decoder.decode(value)


encodings_settings = EncodingsSettings()
