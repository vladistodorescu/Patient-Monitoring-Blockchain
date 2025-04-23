# PMBAppBackEnd.py
from flask import Flask, request, jsonify

print("🚀 Running the latest app.py version with 5 initial patients")

app = Flask(__name__)

vitals_data = []

@app.route("/", methods=["GET"])
def home():
    return "Vitals API is running!"

@app.route("/vitals", methods=["POST"])
def post_vitals():
    data = request.json
    vitals_data.append(data)
    print("Received:", data)
    return jsonify({"status": "ok", "alert": data.get("pulse", 0) > 120})
     
@app.route("/vitals", methods=["GET"])
def get_vitals():
    return jsonify(vitals_data)

# Generates 5 Patients with random vitals 
def generate_fake_vitals(patient_id):
    import random
    return {
        "patient_id": patient_id,
        "pulse": random.randint(60, 140),
        "spo2": random.randint(90, 100),
        "bp": f"{random.randint(100, 140)}/{random.randint(60, 90)}"
    }

# Add 5 fake patients at startup
for i in range(5):
    fake = generate_fake_vitals(f"patient_{i+1}")
    vitals_data.append(fake)
    print("✅ Spawned:", fake)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=8080)
