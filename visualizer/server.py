from flask import Flask, send_from_directory, jsonify
import os, json

app = Flask(__name__, static_folder="web")

@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/blockchain")
def blockchain():
    return send_from_directory("web", "blockchain.html")

@app.route("/graph.json")
def graph_json():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "graph.json")
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return jsonify({"nodes": [], "links": []})
    with open(path) as f:
        return jsonify(json.load(f))


@app.route("/analytics.json")
def analytics_json():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "analytics.json")
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return jsonify({
            "policy": {"runs": [], "average": {}},
            "latency": {"runs": [], "average": []},
            "throughput": {"windows": [], "summary_runs": [], "summary_average": {}, "slo_p95_ms": 50.0},
            "network_tps": {"runs": [], "average": {}},
            "audit": [],
            "audit_summary": {},
        })
    with open(path) as f:
        return jsonify(json.load(f))


@app.route("/data/<path:filename>")
def data_files(filename: str):
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    return send_from_directory(data_dir, filename)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5005, debug=False)
