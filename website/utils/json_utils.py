import uuid
from datetime import datetime as dt


def serialize(d: dict) -> dict:
    updated = {}
    for key, value in d.items():
        if isinstance(key, uuid.UUID):
            key = str(key)
        if isinstance(value, dict):
            updated[key] = serialize(value)
        elif isinstance(value, list):
            updated[key] = [serialize(i) for i in value]
        elif isinstance(value, (str, int, bool)):
            updated[key] = value
        elif isinstance(value, uuid.UUID):
            updated[key] = str(value)
        elif isinstance(value, dt):
            updated[key] = value.isoformat()
        elif value is None:
            updated[key] = None
        else:
            raise ValueError("Can't process type %s" % type(value))
    return updated
