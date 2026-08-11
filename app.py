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
        scanned = scan_collection(url)
    except ScrapeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 - surface any fetch/parsing failure to the UI
        return jsonify({"error": f"Scan failed: {e}"}), 502

    data, newly_added = store.merge_scanned(scanned, url)
    failed = [m.workshop_id for m in scanned if not m.ok]
    no_mod_id = [m.workshop_id for m in scanned if m.ok and not m.mod_ids]
    return jsonify(
        {
            "data": data,
            "scannedCount": len(scanned),
            "newlyAdded": newly_added,
            "failed": failed,
            "noModId": no_mod_id,
        }
    )


@app.post("/api/reorder")
def reorder():
    body = request.get_json(force=True, silent=True) or {}
    order = body.get("order")
    if not isinstance(order, list):
        return jsonify({"error": "Expected {order: [workshopId, ...]}"}), 400
    return jsonify(store.reorder(order))


@app.post("/api/mods/<workshop_id>")
def edit_mod(workshop_id):
    body = request.get_json(force=True, silent=True) or {}
    mod_ids = body.get("modIds")
    name = body.get("name")
    try:
        data = store.update_mod(workshop_id, mod_ids=mod_ids, name=name)
    except KeyError:
        return jsonify({"error": "Unknown workshop id."}), 404
    return jsonify(data)


@app.delete("/api/mods/<workshop_id>")
def delete_mod(workshop_id):
    return jsonify(store.remove(workshop_id))


@app.post("/api/clear")
def clear_all():
    return jsonify(store.clear())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
