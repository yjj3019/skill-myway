"""Choose the next devlog sync action from an authorized reader's snapshot."""
import json
import sys


def unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate snapshot key")
        result[key] = value
    return result


def reconcile(snapshot):
    entry_id = snapshot["entry_id"]
    body = snapshot["body"]
    state = snapshot["state"]
    complete = snapshot["complete"]
    entries = snapshot["entries"]
    if not isinstance(entry_id, str) or not entry_id.strip() or not isinstance(body, str) or not body.strip():
        raise ValueError("expected a persisted ID and body")
    if state not in ("ready", "pending") or type(complete) is not bool or not isinstance(entries, list):
        raise ValueError("invalid sync state or scan")
    matches = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("entry_id"), str) or not isinstance(entry.get("body"), str):
            raise ValueError("invalid remote entry")
        if entry["entry_id"] == entry_id:
            matches.append(entry["body"])
    if len(matches) > 1 or (matches and matches[0] != body):
        return "conflict"
    if not complete:
        return "hold"
    if matches:
        return "synced"
    return "append" if state == "ready" else "hold"


if __name__ == "__main__":
    try:
        print(reconcile(json.load(sys.stdin, object_pairs_hook=unique_members)))
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        sys.exit(f"Invalid snapshot: {error}")
