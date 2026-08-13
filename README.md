# PZ Mod Grabber

A small local tool that scans a Steam Workshop **collection** for a Project
Zomboid server, keeps a maintainable list of `Mod ID` / `Workshop ID` / name
for every item, and gives you a UI to reorder that list and copy the
`Mods=` / `WorkshopItems=` lines straight into `servertest.ini`.

Compared to a one-off browser console script, this keeps a persistent list:
re-scanning the same (or a different) collection **adds new mods to the
list without touching or duplicating what's already there**, and load order
you've arranged by hand survives a rescan. Each collection you scan is
tracked separately, so you can see which mods came from which collection,
reorder the collections, or delete a whole collection at once.

## How it works

- The server (`app.py`) calls Steam's own Web API — `GetCollectionDetails`
  to list every item id in the collection, then `GetPublishedFileDetails`
  in batches of up to 100 to pull each item's title and description in one
  shot. That's **2-3 HTTP requests total, no matter how big the collection
  is** — no per-mod page fetching, so it doesn't get rate-limited (earlier
  versions of this tool scraped one Workshop page per mod and hit Steam's
  429 after ~10-15 mods; this doesn't have that problem).
- `Mod ID:` / `MID:` (and, if present, `Map Folder:`) lines are pulled out
  of each item's description with a regex, same convention the well-known
  browser-console versions of this tool use.
- Everything is saved to `data/mods.json`. That file *is* your list — back
  it up / commit it / edit it by hand if you want.
- The web UI is just a thin client over a small JSON API (`/api/mods`,
  `/api/scan`, `/api/reorder`, `/api/reorder-collections`,
  `/api/mods/<id>`, `/api/collections/<id>`, `/api/clear`).
- No API key needed. These two `ISteamRemoteStorage` endpoints are public
  and don't require auth (they're what SteamCMD and most Workshop tools use
  under the hood). If Valve ever changes that, set a `STEAM_API_KEY`
  environment variable (free from https://steamcommunity.com/dev/apikey)
  before running `app.py` and it'll be sent automatically.

## Setup

```bash
cd pz-mod-grabber
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5050 in your browser.

## Using it

1. Paste a Workshop **collection** URL (`.../sharedfiles/filedetails/?id=...`
   pointing at a collection, not a single mod) and hit **Scan collection**.
2. New mods appear at the bottom of their collection. Drag the ⠿ handle to
   reorder mods within a collection, and drag a collection to change the
   order the collections appear in (and are output) — load order matters in
   PZ for some mods (frameworks before the mods that need them, tile packs
   before maps that use them, etc.).
3. If a mod shows "no Mod ID found" or "N mod ids — verify", open its
   Workshop page, check the description, and edit the Mod ID field directly
   in the list (it saves on blur/Enter).
4. Toggle **Build 42 format** if your server is on B42+ (prefixes each Mod
   ID with `\`, per PZ's current config format). Turn it off for Build 41.
5. Hit **Copy** next to `Mods=` and `WorkshopItems=` and paste both lines
   into your server's `.ini`. A `Map=` line appears too if any scanned mod
   declares a map folder.
6. Re-run a scan on the same collection any time you add mods to it on
   Steam — only the new ones get appended, nothing gets reshuffled. Scan a
   second collection and its mods are added under a new heading; delete a
   collection with its ✕ button to remove it (and any mods that only live
   there) all at once.

## Notes / limitations

- Steam doesn't put a machine-readable Mod ID anywhere except free-text in
  the description, so extraction is regex-based (`Mod ID:` / `MID:`). Most
  authors follow the convention; a few don't put it in the description at
  all — those show up flagged in the UI so you can fill them in by hand.
- A collection must be **public** for the Steam API to read it.
- `data/mods.json` is per-machine local storage; nothing is sent anywhere
  except to Steam's own API to read public Workshop data.
