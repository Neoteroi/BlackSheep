from blacksheep.settings.json import json_settings

from .abc import Session, SessionSerializer


class JSONSerializer(SessionSerializer):
    """
    Serializes and deserializes Session objects using JSON format.

    This serializer uses the application's JSON settings to convert session data
    to and from JSON strings, enabling storage and retrieval of session information
    in a widely supported text format.
    """

    def read(self, value: str) -> Session:
        return Session(json_settings.loads(value))

    def write(self, session: Session) -> str:
        return json_settings.dumps(session.to_dict())
