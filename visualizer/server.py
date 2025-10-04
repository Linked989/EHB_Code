from flask import Flask, send_from_directory, jsonify
import os, json

app = Flask(__name__, static_folder="web")

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

@app.route("/graph.json")
def graph_json():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "graph.json")
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return jsonify({"nodes": [], "links": []})
    with open(path) as f:
        return jsonify(json.load(f))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5005, debug=False)
