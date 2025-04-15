# PMBAppBackEnd.py
from flask import Flask, request, jsonify
from datetime import datetime
from AlertLogicBackend import check_alert
from DataStoreBackend import store_vitals, read_all_vitals

app = Flask(__name__)

@app.route("/")
def index():
    return "<h2>✅ PMB API active. POST to /vitals or view data at /view</h2>"

@app.route("/vitals", methods=["POST"])
def post_vitals():
    data = request.json
    data["timestamp"] = datetime.utcnow().isoformat()
    store_vitals(data)
    alert = check_alert(data)
    return jsonify({"status": "ok", "alert": alert})

@app.route("/view", methods=["GET"])
def view_vitals():
    vitals = read_all_vitals()
    rows = ""
    for v in vitals:
        rows += f"<tr><td>{v['timestamp']}</td><td>{v['patient_id']}</td><td>{v['heart_rate']}</td><td>{v['bp_sys']}</td><td>{v['bp_dia']}</td><td>{v['spo2']}</td></tr>"
    return f"""
    <h2>📊 Patient Vitals Log</h2>
    <table border="1" cellpadding="8" style="font-family: monospace;">
        <tr><th>Time</th><th>ID</th><th>HR</th><th>BP SYS</th><th>BP DIA</th><th>SpO₂</th></tr>
        {rows}
    </table>
    """

@app.route("/export/json", methods=["GET"])
def export_json():
    return jsonify(read_all_vitals())

if __name__ == "__main__":
    app.run(debug=True)

