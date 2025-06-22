from abc import ABC, abstractmethod


class Decoder(ABC):
    """
    Abstract base class for byte sequence decoders.

    Implementations of this class provide a strategy for decoding bytes into
    strings, used when a UnicodeDecodeError occurs during standard
    decoding. Subclasses must implement the `decode` method, which receives
    the bytes to decode and the original UnicodeDecodeError.

    Methods:
        decode(value: bytes, decode_error: UnicodeDecodeError) -> str:
            Attempts to decode the given bytes. Should raise the provided
            decode_error if decoding is not possible.
    """

    @abstractmethod
    def decode(self, value: bytes, decode_error: UnicodeDecodeError) -> str: ...


class NoopDecoder(Decoder):
    """
    A decoder implementation that does not attempt to decode input bytes.

    This class always raises the provided UnicodeDecodeError when its decode
    method is called. It can be used to disable automatic encoding detection
    and force strict decoding behavior, ensuring that decoding errors are
    not silently handled or guessed.

    Methods:
        decode(value: bytes, decode_error: UnicodeDecodeError) -> str:
            Always raises the provided decode_error.
    """

    def decode(self, value: bytes, decode_error: UnicodeDecodeError) -> str:
        raise decode_error


class EncodingsSettings:
    """
    Manages the decoding strategy for byte sequences in the application.

    EncodingsSettings allows configuring which Decoder implementation is used
    to decode bytes when a UnicodeDecodeError occurs. By default, it uses
    NoopDecoder, which does not attempt to detect the encoding and re-raises the
    UnicodeDecodeError for further processing. The decoder can be replaced at runtime
    using the `use` method.

    Methods:
        use(decoder: Decoder) -> None:
            Sets the decoder to be used for decoding operations.

        decode(value: bytes, decode_error: UnicodeDecodeError) -> str:
            Decodes the given bytes using the configured decoder. If decoding fails,
            the provided UnicodeDecodeError is raised or handled according to the
            decoder.
    """

    def __init__(self) -> None:
        self._decoder = NoopDecoder()

    def use(self, decoder: Decoder) -> None:
        self._decoder = decoder

    def decode(self, value: bytes, decode_error: UnicodeDecodeError) -> str:
        return self._decoder.decode(value, decode_error)


encodings_settings = EncodingsSettings()
