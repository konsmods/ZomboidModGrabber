"""
Tiny JSON-file store for the maintained mod list.

Shape of data/mods.json:
{
  "order": ["<workshop_id>", ...],           # display / config order
  "mods": {
    "<workshop_id>": {
        "workshopId": "...",
        "name": "...",
        "modIds": ["...", ...],
        "maps": ["...", ...],
        "collectionUrl": "...",
        "ok": true,
        "error": ""
    }
  }
}

Re-scanning a collection never deletes or reorders what you already have -
it only updates the name/modIds/maps of items you already saved, and adds
newly-found items to the end of "order". Reordering, editing and removing
happen through the UI (which just calls the /api/* endpoints below).
"""

from __future__ import annotations

import json
import os
import threading

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "mods.json")
_lock = threading.Lock()


def _empty():
    return {"order": [], "mods": {}}


def load() -> dict:
    if not os.path.exists(DATA_PATH):
        return _empty()
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return _empty()
    data.setdefault("order", [])
    data.setdefault("mods", {})
    return data


def save(data: dict) -> None:
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    tmp_path = DATA_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, DATA_PATH)


def merge_scanned(scanned_mods, collection_url: str) -> tuple[dict, list[str]]:
    """Merge freshly scanned mods into the store.

    Existing entries: name/modIds/maps/ok/error refreshed in place, position
    in "order" left untouched (so manual reordering survives a rescan).
    New entries: appended to the end of "order".

    Returns (updated_store, list_of_newly_added_workshop_ids).
    """
    with _lock:
        data = load()
        newly_added = []

        for mod in scanned_mods:
            wsid = mod.workshop_id
            existing = data["mods"].get(wsid)
            entry = {
                "workshopId": wsid,
                "name": mod.name,
                "modIds": mod.mod_ids,
                "maps": mod.maps,
                "collectionUrl": collection_url,
                "ok": mod.ok,
                "error": mod.error,
            }
            if existing is None:
                data["mods"][wsid] = entry
                data["order"].append(wsid)
                newly_added.append(wsid)
            else:
                # keep it in place, just refresh the details.
                # If the scanned mod_ids is empty but the user manually
                # entered some, preserve the manual values.
                if not entry["modIds"] and existing.get("modIds"):
                    del entry["modIds"]
                existing.update(entry)

        save(data)
        return data, newly_added


def reorder(new_order: list[str]) -> dict:
    with _lock:
        data = load()
        known = set(data["order"])
        cleaned = [wsid for wsid in new_order if wsid in known]
        # anything missing from the submitted order (shouldn't happen) stays put at the end
        for wsid in data["order"]:
            if wsid not in cleaned:
                cleaned.append(wsid)
        data["order"] = cleaned
        save(data)
        return data


def remove(workshop_id: str) -> dict:
    with _lock:
        data = load()
        data["order"] = [w for w in data["order"] if w != workshop_id]
        data["mods"].pop(workshop_id, None)
        save(data)
        return data


def update_mod(workshop_id: str, mod_ids: list[str] | None = None, name: str | None = None) -> dict:
    with _lock:
        data = load()
        entry = data["mods"].get(workshop_id)
        if entry is None:
            raise KeyError(workshop_id)
        if mod_ids is not None:
            entry["modIds"] = mod_ids
        if name is not None:
            entry["name"] = name
        save(data)
        return data


def clear() -> dict:
    with _lock:
        data = _empty()
        save(data)
        return data
