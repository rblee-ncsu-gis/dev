"""Stream local GeoJSON FeatureCollections using only the standard JSON decoder.

County exports need not be decoded into a second, whole-file copy in memory.
Events preserve top-level declarations even when they follow the features array.
"""

import json


class _Reader:
    def __init__(self, stream):
        self.stream, self.buffer, self.position, self.eof = stream, "", 0, False
        self.decoder = json.JSONDecoder()

    def fill(self):
        data = self.stream.read(65536)
        self.buffer = self.buffer[self.position:] + data
        self.position = 0
        self.eof = not data

    def peek(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ""
            self.fill()

    def expect(self, token):
        if self.peek() != token:
            raise ValueError(f"Invalid GeoJSON syntax: expected {token!r}")
        self.position += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                if end == len(self.buffer) and not self.eof:
                    self.fill()
                    continue
                self.position = end
                return value
            except json.JSONDecodeError as exc:
                if self.eof:
                    raise ValueError(f"Invalid GeoJSON JSON: {exc.msg}") from exc
                self.fill()


def collection_events(path, *, require_feature_collection=True):
    """Yield (header, (key,value)) and (feature, object); reject malformed roots."""
    with open(path, encoding="utf-8-sig") as stream:
        reader = _Reader(stream)
        reader.expect("{")
        seen, declared_type = set(), None
        while reader.peek() != "}":
            key = reader.value()
            if not isinstance(key, str) or key in seen:
                raise ValueError("GeoJSON root keys must be unique strings")
            seen.add(key)
            reader.expect(":")
            if key == "features":
                reader.expect("[")
                while reader.peek() != "]":
                    yield "feature", reader.value()
                    if reader.peek() == "]":
                        break
                    reader.expect(",")
                    if reader.peek() == "]":
                        raise ValueError("Trailing comma in GeoJSON features")
                reader.expect("]")
            else:
                value = reader.value()
                if key == "type":
                    declared_type = value
                yield "header", (key, value)
            if reader.peek() == "}":
                break
            reader.expect(",")
            if reader.peek() == "}":
                raise ValueError("Trailing comma in GeoJSON root")
        reader.expect("}")
        if reader.peek() or require_feature_collection and declared_type != "FeatureCollection" or "features" not in seen:
            raise ValueError("Expected exactly one GeoJSON FeatureCollection")
