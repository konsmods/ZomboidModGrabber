"""
Scraper for Steam Workshop collections -> Project Zomboid mod/workshop IDs.

v2: uses Steam's Web API instead of scraping one HTML page per mod.

The old approach (fetch the collection page, then fetch every single mod's
page individually to read its description) does 1 + N requests and gets
rate-limited (HTTP 429) by steamcommunity.com once N gets much past ~10-15.

Steam's public ISteamRemoteStorage API does the same job in two batched
POST requests, regardless of collection size:

  1. GetCollectionDetails - given the collection's id, returns every child
     item's id, in collection order.
  2. GetPublishedFileDetails - given up to ~100 ids at a time, returns each
     item's title + full description in one response.

Both endpoints are the same ones SteamCMD / most community Workshop tools
use, and work without an API key. If Valve ever starts requiring one for
these, set the STEAM_API_KEY environment variable and it'll be sent along
automatically.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests

STEAM_API_BASE = "https://api.steampowered.com"
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "").strip()

USER_AGENT = "pz-mod-grabber/2.0 (+local tool)"

MOD_ID_RE = re.compile(r"^\s*(?:Mod\s*ID|MID)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
MAP_RE = re.compile(r"^\s*(?:Map\s*Folder|Folder|Map)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

BATCH_SIZE = 100  # Steam's GetPublishedFileDetails gets unreliable much above this


class ScrapeError(Exception):
    pass


@dataclass
class ScannedMod:
    workshop_id: str
    name: str = ""
    mod_ids: list[str] = field(default_factory=list)
    maps: list[str] = field(default_factory=list)
    ok: bool = True
    error: str = ""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _dedupe(seq):
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def extract_collection_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    m = re.search(r"[?&]id=(\d+)", url_or_id)
    if m:
        return m.group(1)
    if url_or_id.isdigit():
        return url_or_id
    raise ScrapeError(
        "Couldn't find a Workshop id in that input. Paste the full collection URL "
        "(.../sharedfiles/filedetails/?id=XXXXXXXXX) or just the numeric id."
    )


def _post(session: requests.Session, path: str, data: dict) -> dict:
    if STEAM_API_KEY:
        data = {**data, "key": STEAM_API_KEY}
    resp = session.post(f"{STEAM_API_BASE}{path}", data=data, timeout=30)
    if resp.status_code == 429:
        raise ScrapeError(
            "Steam is rate-limiting these requests (429). Wait a minute or two and try again."
        )
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as e:
        raise ScrapeError(f"Steam returned something that wasn't JSON: {e}") from e


def _get_collection_children(collection_id: str, session: requests.Session) -> list[str]:
    payload = _post(
        session,
        "/ISteamRemoteStorage/GetCollectionDetails/v1/",
        {"collectioncount": 1, "publishedfileids[0]": collection_id},
    )
    details = payload.get("response", {}).get("collectiondetails", [])
    if not details:
        raise ScrapeError("Steam returned no data for that collection id.")

    entry = details[0]
    result_code = entry.get("result")
    if result_code != 1:
        raise ScrapeError(
            f"Steam couldn't load that collection (result code {result_code}). "
            "Make sure the URL points at a public Workshop *collection*, not a single mod."
        )

    children = entry.get("children", [])
    ids = _dedupe(c["publishedfileid"] for c in children if "publishedfileid" in c)
    if not ids:
        raise ScrapeError("That collection doesn't seem to contain any items.")
    return ids


def _get_file_details(ids: list[str], session: requests.Session) -> dict[str, dict]:
    """Fetch title/description for a batch of workshop ids in one POST call."""
    data = {"itemcount": len(ids)}
    for i, wid in enumerate(ids):
        data[f"publishedfileids[{i}]"] = wid

    payload = _post(session, "/ISteamRemoteStorage/GetPublishedFileDetails/v1/", data)
    items = payload.get("response", {}).get("publishedfiledetails", [])
    return {item["publishedfileid"]: item for item in items if "publishedfileid" in item}


def _parse_details(workshop_id: str, item: dict | None) -> ScannedMod:
    if item is None:
        return ScannedMod(workshop_id=workshop_id, ok=False, error="not returned by Steam")

    result_code = item.get("result")
    if result_code is not None and result_code != 1:
        return ScannedMod(
            workshop_id=workshop_id,
            name=item.get("title", ""),
            ok=False,
            error=f"unavailable (result code {result_code}) - likely removed or private",
        )

    name = item.get("title", "")
    text = item.get("file_description") or item.get("description") or ""

    mod_ids = _dedupe(
        part.strip()
        for line in MOD_ID_RE.findall(text)
        for part in re.split(r"[;,]", line)
        if part.strip()
    )
    maps = _dedupe(
        part.strip()
        for line in MAP_RE.findall(text)
        for part in re.split(r"[;,]", line)
        if part.strip()
    )

    return ScannedMod(workshop_id=workshop_id, name=name, mod_ids=mod_ids, maps=maps)


def scan_collection(collection_url: str, max_workers: int = 8) -> list[ScannedMod]:
    """max_workers kept for API compatibility with the caller; unused now that
    fetching is batched rather than one request per mod."""
    session = _session()
    collection_id = extract_collection_id(collection_url)
    ordered_ids = _get_collection_children(collection_id, session)

    details_by_id: dict[str, dict] = {}
    for i in range(0, len(ordered_ids), BATCH_SIZE):
        batch = ordered_ids[i : i + BATCH_SIZE]
        details_by_id.update(_get_file_details(batch, session))

    return [_parse_details(wsid, details_by_id.get(wsid)) for wsid in ordered_ids]
