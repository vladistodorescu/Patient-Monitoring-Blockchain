# DeviceAPI.py
import json
import threading

import paho.mqtt.client as mqtt
from flask import Blueprint, request, jsonify

from DatabaseAppPMB import get_db
from Broadcaster import broadcaster  # use the same broadcaster instance

device_bp = Blueprint('DeviceAPI', __name__)

# ---- FHIR HTTP endpoint ----
@device_bp.route('/fhir', methods=['POST'])
def ingest_fhir_observation():
    obs = request.get_json()
    pid = int(obs['subject']['reference'].split('/')[-1])

    comps = {c['code']['text']: c for c in obs.get('component', [])}
    pulse = comps['pulse']['valueQuantity']['value']
    spo2  = comps['spo2']['valueQuantity']['value']
    bp_comp = comps['bloodPressure']['component']
    sys = next(c for c in bp_comp if c['code']['text']=='systolic')['valueQuantity']['value']
    dia = next(c for c in bp_comp if c['code']['text']=='diastolic')['valueQuantity']['value']
    bp_str = f"{sys}/{dia}"

    _store_and_emit(pid, pulse, spo2, bp_str)
    return jsonify(status="ok"), 201

# ---- MQTT Subscriber ----
MQTT_BROKER = 'localhost'
MQTT_PORT   = 1883
MQTT_TOPIC  = 'devices/+/vitals'

def _on_connect(client, userdata, flags, rc):
    client.subscribe(MQTT_TOPIC)

def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        pid   = int(payload['patient_id'])
        pulse = int(payload['pulse'])
        spo2  = int(payload['spo2'])
        bp_str= payload['bp']
        _store_and_emit(pid, pulse, spo2, bp_str)
    except Exception as e:
        print("❌ MQTT error:", e)

def start_mqtt():
    client = mqtt.Client()
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(MQTT_BROKER, MQTT_PORT)
    threading.Thread(target=client.loop_forever, daemon=True).start()

start_mqtt()

# ---- Shared persistence & broadcast helper ----
def _store_and_emit(patient_id, pulse, spo2, bp_str):
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vitals(patient_id,pulse,bp,spo2) "
                "VALUES (%s,%s,%s,%s) RETURNING timestamp;",
                (patient_id, pulse, bp_str, spo2)
            )
            row = cur.fetchone()
            ts  = row['timestamp']
    msg = json.dumps({
        "id":        patient_id,
        "pulse":     pulse,
        "bp":        bp_str,
        "spo2":      spo2,
        "timestamp": ts.isoformat()
    })
    broadcaster.broadcast(msg)
