"""Decode UTF-8 JSON contracts without silently overwriting object members."""
import json


def _members(pairs):
    obj = {}
    for name, value in pairs:
        if name in obj:
            raise ValueError("duplicate JSON key")
        obj[name] = value
    return obj


def _invalid_number(token):
    raise ValueError(f"invalid JSON number: {token}")


def loads(text):
    return json.loads(text, object_pairs_hook=_members, parse_constant=_invalid_number)
