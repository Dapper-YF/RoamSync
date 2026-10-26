"""Lossless, request-local model references; never infer an unknown entity."""
import re
from typing import Any


_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_REF = re.compile(r"\bref_\d{4}\b")


class PlannerReferenceCodec:
    def __init__(self, prompt: dict) -> None:
        identifiers: set[str] = set()

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    collect(key)
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, str) and _UUID.fullmatch(value):
                identifiers.add(value)

        collect(prompt)
        self.encode_map = {value: f"ref_{index:04d}" for index, value in enumerate(sorted(identifiers), 1)}
        self.decode_map = {value: key for key, value in self.encode_map.items()}

    def encode(self, value: Any, *, schema: bool = False) -> Any:
        if isinstance(value, dict):
            return {self.encode(key): self.encode(item, schema=schema) for key, item in value.items()
                    if not (schema and key == "format" and item == "uuid")}
        if isinstance(value, list):
            return [self.encode(item, schema=schema) for item in value]
        if isinstance(value, str):
            return _UUID.sub(lambda match: self.encode_map.get(match[0], match[0]), value)
        return value

    def decode(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {self.decode(key): self.decode(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.decode(item) for item in value]
        if isinstance(value, str):
            # Unissued tokens remain invalid; no name matching or nearest-ID repair.
            return _REF.sub(lambda match: self.decode_map.get(match[0], match[0]), value)
        return value
