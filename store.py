"""
Tiny JSON-file store for the maintained mod list.

Shape of data/mods.json:
{
  "collectionOrder": ["<collection_id>", ...],   # display / output order of collections
  "collections": {
    "<collection_id>": {
        "id": "...",
        "url": "...",
        "name": "...",
        "order": ["<workshop_id>", ...]
    }
  },
  "mods": {
    "<workshop_id>": {
        "workshopId": "...",
        "name": "...",
        "modIds": ["...", ...],
        "maps": ["...", ...],
        "collectionIds": ["<collection_id>", ...],
        "ok": true,
        "error": ""
    }
  }
}

Re-scanning a collection updates the name/modIds/maps of items you already
saved, adds newly-found items to the end of that collection's "order", and
removes items that no longer exist in the collection on Steam. Your own
order is always preserved (Steam's ordering is ignored). Collections are
reorderable and can be deleted as a whole from the UI.
"""

from __future__ import annotations

import json
import os
import re
import threading
from contextvars import ContextVar

from scraper import canonical_collection_url, extract_collection_id, ScrapeError

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "mods.json")
PRESETS_DIR = os.path.join(os.path.dirname(DATA_PATH), "presets")
PRESET_META_PATH = os.path.join(os.path.dirname(DATA_PATH), "presets.json")
DEFAULT_PRESET = "default"
_preset_id = ContextVar("preset_id", default=DEFAULT_PRESET)
_lock = threading.Lock()


class PresetError(ValueError):
    pass


def _preset_path(preset_id: str) -> str:
    if preset_id == DEFAULT_PRESET:
        return DATA_PATH
    return os.path.join(PRESETS_DIR, f"{preset_id}.json")


def _valid_preset_id(preset_id: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", preset_id))


def current_preset() -> str:
    return _preset_id.get()


def activate_preset(preset_id: str) -> None:
    if not _valid_preset_id(preset_id):
        raise PresetError("Invalid preset id.")
    if preset_id != DEFAULT_PRESET and not os.path.isfile(_preset_path(preset_id)):
        raise PresetError(f"Unknown preset: {preset_id}")
    _preset_id.set(preset_id)


def reset_preset() -> None:
    _preset_id.set(DEFAULT_PRESET)


def _preset_names() -> dict[str, str]:
    if not os.path.exists(PRESET_META_PATH):
        return {}
    try:
        with open(PRESET_META_PATH, "r", encoding="utf-8") as f:
            names = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return names if isinstance(names, dict) else {}


def _write_preset_names(names: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(PRESET_META_PATH), exist_ok=True)
    tmp_path = PRESET_META_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(names, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, PRESET_META_PATH)


def list_presets() -> list[dict[str, str]]:
    with _lock:
        ids = [DEFAULT_PRESET]
        if os.path.isdir(PRESETS_DIR):
            ids.extend(
                filename[:-5]
                for filename in os.listdir(PRESETS_DIR)
                if filename.endswith(".json")
                and _valid_preset_id(filename[:-5])
                and filename[:-5] != DEFAULT_PRESET
            )
        names = _preset_names()
        return [
            {"id": preset_id, "name": names.get(preset_id, "Default" if preset_id == DEFAULT_PRESET else preset_id)}
            for preset_id in sorted(set(ids), key=lambda value: (value != DEFAULT_PRESET, value))
        ]


def presets_state() -> dict:
    return {"presets": list_presets(), "active": current_preset()}


def create_preset(name: str) -> tuple[str, dict]:
    name = (name or "").strip()
    preset_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    if not preset_id or not _valid_preset_id(preset_id) or preset_id == DEFAULT_PRESET:
        raise PresetError("Use a unique preset name other than 'default'.")
    with _lock:
        path = _preset_path(preset_id)
        if os.path.exists(path):
            raise PresetError("A preset with that name already exists.")
        _save_path(_empty(), path)
        names = _preset_names()
        names[preset_id] = name
        _write_preset_names(names)
        _preset_id.set(preset_id)
        return preset_id, _empty()


def delete_preset(preset_id: str) -> None:
    if preset_id == DEFAULT_PRESET:
        raise PresetError("The default preset cannot be deleted.")
    with _lock:
        path = _preset_path(preset_id)
        if not os.path.isfile(path):
            raise PresetError(f"Unknown preset: {preset_id}")
        os.remove(path)
        names = _preset_names()
        names.pop(preset_id, None)
        _write_preset_names(names)
        if current_preset() == preset_id:
            _preset_id.set(DEFAULT_PRESET)


def _empty():
    return {"collectionOrder": [], "collections": {}, "mods": {}}


def _migrate(data: dict) -> dict:
    """Upgrade the old single-collection schema to the multi-collection one."""
    if "collections" in data and "collectionOrder" in data:
        return data

    mods = data.get("mods", {})
    order = data.get("order", [])

    collections: dict[str, dict] = {}
    collection_order: list[str] = []

    for wsid in order:
        mod = mods.get(wsid)
        if not mod:
            continue
        url = mod.pop("collectionUrl", None)
        if not url:
            continue
        try:
            cid = extract_collection_id(url)
        except ScrapeError:
            continue

        if cid not in collections:
            collections[cid] = {
                "id": cid,
                "url": canonical_collection_url(url),
                "name": "",
                "order": [],
                "enabled": True,
            }
            collection_order.append(cid)

        collections[cid]["order"].append(wsid)
        mod.setdefault("collectionIds", [])
        if cid not in mod["collectionIds"]:
            mod["collectionIds"].append(cid)
        mod.setdefault("disabledModIds", [])
        mod.setdefault("enabled", True)

    data["collections"] = collections
    data["collectionOrder"] = collection_order
    data.pop("order", None)
    return data


def load() -> dict:
    path = _preset_path(current_preset())
    if not os.path.exists(path):
        return _empty()
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return _empty()
    if not isinstance(data, dict):
        return _empty()
    data = _migrate(data)
    data.setdefault("collectionOrder", [])
    data.setdefault("collections", {})
    data.setdefault("mods", {})
    return data


def _save_path(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def save(data: dict) -> None:
    _save_path(data, _preset_path(current_preset()))


def merge_scanned(collection_url: str, collection_name: str, scanned_mods) -> tuple[dict, list[str], list[str]]:
    """Merge freshly scanned mods into the store, grouped under their collection.

    Existing entries: name/modIds/maps/ok/error refreshed in place. New entries
    are appended to the end of the collection's "order" (Steam's order is ignored,
    so our established order is preserved). Mods that disappeared from the
    collection on Steam are removed; if a removed mod belongs to no other
    collection, it is dropped entirely.

    Returns (updated_store, list_of_newly_added_workshop_ids, list_of_removed_workshop_ids).
    """
    with _lock:
        data = load()
        cid = extract_collection_id(collection_url)

        collection = data["collections"].get(cid)
        if collection is None:
            collection = {
                "id": cid,
                "url": canonical_collection_url(collection_url),
                "name": collection_name,
                "order": [],
                "enabled": True,
            }
            data["collections"][cid] = collection
            data["collectionOrder"].append(cid)
        else:
            collection["url"] = canonical_collection_url(collection_url)
            if collection_name:
                collection["name"] = collection_name
            collection.setdefault("enabled", True)

        scanned_ids = {mod.workshop_id for mod in scanned_mods}

        # Drop mods that were removed from the collection on Steam, keeping
        # our established order for everything that remains.
        removed = []
        kept = []
        for wsid in collection["order"]:
            if wsid in scanned_ids:
                kept.append(wsid)
                continue
            removed.append(wsid)
            mod = data["mods"].get(wsid)
            if mod:
                mod["collectionIds"] = [c for c in mod.get("collectionIds", []) if c != cid]
                if not mod["collectionIds"]:
                    data["mods"].pop(wsid, None)
        collection["order"] = kept

        newly_added = []

        for mod in scanned_mods:
            wsid = mod.workshop_id
            existing = data["mods"].get(wsid)
            entry = {
                "workshopId": wsid,
                "name": mod.name,
                "modIds": mod.mod_ids,
                "maps": mod.maps,
                "ok": mod.ok,
                "error": mod.error,
            }
            if existing is None:
                entry["collectionIds"] = [cid]
                entry["disabledModIds"] = []
                entry["enabled"] = True
                data["mods"][wsid] = entry
                collection["order"].append(wsid)
                newly_added.append(wsid)
            else:
                # keep it in place, just refresh the details.
                # If the scanned mod_ids is empty but the user manually
                # entered some, preserve the manual values.
                if not entry["modIds"] and existing.get("modIds"):
                    del entry["modIds"]
                existing.setdefault("disabledModIds", [])
                existing.setdefault("enabled", True)
                existing.update(entry)
                existing.setdefault("collectionIds", [])
                if cid not in existing["collectionIds"]:
                    existing["collectionIds"].append(cid)
                if wsid not in collection["order"]:
                    collection["order"].append(wsid)

        save(data)
        return data, newly_added, removed


def reorder_collections(new_order: list[str]) -> dict:
    with _lock:
        data = load()
        known = set(data["collectionOrder"])
        cleaned = [cid for cid in new_order if cid in known]
        # anything missing from the submitted order (shouldn't happen) stays put at the end
        for cid in data["collectionOrder"]:
            if cid not in cleaned:
                cleaned.append(cid)
        data["collectionOrder"] = cleaned
        save(data)
        return data


def reorder_collection(collection_id: str, new_order: list[str]) -> dict:
    with _lock:
        data = load()
        collection = data["collections"].get(collection_id)
        if collection is None:
            raise KeyError(collection_id)
        known = set(collection.get("order", []))
        cleaned = [wsid for wsid in new_order if wsid in known]
        for wsid in collection.get("order", []):
            if wsid not in cleaned:
                cleaned.append(wsid)
        collection["order"] = cleaned
        save(data)
        return data


def delete_collection(collection_id: str) -> dict:
    with _lock:
        data = load()
        collection = data["collections"].pop(collection_id, None)
        if collection is None:
            raise KeyError(collection_id)
        data["collectionOrder"] = [c for c in data["collectionOrder"] if c != collection_id]
        for wsid in collection.get("order", []):
            mod = data["mods"].get(wsid)
            if not mod:
                continue
            mod["collectionIds"] = [c for c in mod.get("collectionIds", []) if c != collection_id]
            if not mod["collectionIds"]:
                data["mods"].pop(wsid, None)
        save(data)
        return data


def remove(workshop_id: str) -> dict:
    with _lock:
        data = load()
        data["mods"].pop(workshop_id, None)
        for collection in data["collections"].values():
            collection["order"] = [w for w in collection.get("order", []) if w != workshop_id]
        save(data)
        return data


def update_mod(workshop_id: str, mod_ids: list[str] | None = None, name: str | None = None, disabled_mod_ids: list[str] | None = None, enabled: bool | None = None) -> dict:
    with _lock:
        data = load()
        entry = data["mods"].get(workshop_id)
        if entry is None:
            raise KeyError(workshop_id)
        if mod_ids is not None:
            entry["modIds"] = mod_ids
        if name is not None:
            entry["name"] = name
        if disabled_mod_ids is not None:
            entry["disabledModIds"] = disabled_mod_ids
        if enabled is not None:
            entry["enabled"] = enabled
        save(data)
        return data


def update_collection(collection_id: str, enabled: bool | None = None) -> dict:
    with _lock:
        data = load()
        collection = data["collections"].get(collection_id)
        if collection is None:
            raise KeyError(collection_id)
        if enabled is not None:
            collection["enabled"] = enabled
        save(data)
        return data


def clear() -> dict:
    with _lock:
        data = _empty()
        save(data)
        return data
