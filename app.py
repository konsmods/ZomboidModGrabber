from flask import Flask, jsonify, request, render_template

import store
from scraper import scan_collection, ScrapeError

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/mods")
def get_mods():
    return jsonify(store.load())


@app.post("/api/scan")
def scan():
    body = request.get_json(force=True, silent=True) or {}
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Missing collection URL."}), 400

    try:
        result = scan_collection(url)
    except ScrapeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 - surface any fetch/parsing failure to the UI
        return jsonify({"error": f"Scan failed: {e}"}), 502

    scanned = result.mods
    data, newly_added, removed = store.merge_scanned(url, result.name, scanned)
    failed = [m.workshop_id for m in scanned if not m.ok]
    no_mod_id = [m.workshop_id for m in scanned if m.ok and not m.mod_ids]
    return jsonify(
        {
            "data": data,
            "scannedCount": len(scanned),
            "newlyAdded": newly_added,
            "removed": removed,
            "failed": failed,
            "noModId": no_mod_id,
        }
    )


@app.post("/api/reorder")
def reorder():
    body = request.get_json(force=True, silent=True) or {}
    order = body.get("order")
    collection = body.get("collection")
    if not isinstance(order, list) or not isinstance(collection, str):
        return jsonify({"error": "Expected {collection: <id>, order: [workshopId, ...]}"}), 400
    try:
        return jsonify(store.reorder_collection(collection, order))
    except KeyError:
        return jsonify({"error": "Unknown collection."}), 404


@app.post("/api/reorder-collections")
def reorder_collections():
    body = request.get_json(force=True, silent=True) or {}
    order = body.get("order")
    if not isinstance(order, list):
        return jsonify({"error": "Expected {order: [collectionId, ...]}"}), 400
    return jsonify(store.reorder_collections(order))


@app.post("/api/mods/<workshop_id>")
def edit_mod(workshop_id):
    body = request.get_json(force=True, silent=True) or {}
    mod_ids = body.get("modIds")
    name = body.get("name")
    disabled_mod_ids = body.get("disabledModIds")
    enabled = body.get("enabled")
    try:
        data = store.update_mod(workshop_id, mod_ids=mod_ids, name=name, disabled_mod_ids=disabled_mod_ids, enabled=enabled)
    except KeyError:
        return jsonify({"error": "Unknown workshop id."}), 404
    return jsonify(data)


@app.post("/api/collections/<collection_id>")
def update_collection(collection_id):
    body = request.get_json(force=True, silent=True) or {}
    enabled = body.get("enabled")
    try:
        return jsonify(store.update_collection(collection_id, enabled=enabled))
    except KeyError:
        return jsonify({"error": "Unknown collection."}), 404


@app.delete("/api/mods/<workshop_id>")
def delete_mod(workshop_id):
    return jsonify(store.remove(workshop_id))


@app.delete("/api/collections/<collection_id>")
def delete_collection(collection_id):
    try:
        return jsonify(store.delete_collection(collection_id))
    except KeyError:
        return jsonify({"error": "Unknown collection."}), 404


@app.post("/api/clear")
def clear_all():
    return jsonify(store.clear())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
