# DeviceAPI.py
import json
import threading
import paho.mqtt.client as mqtt
from flask import Blueprint, request, jsonify
from DatabaseAppPMB import get_db
from Broadcaster import broadcaster

device_bp = Blueprint('device_api', __name__)

@device_bp.route('/fhir', methods=['POST'])
def ingest_fhir_observation():
    obs = request.get_json()
    pid = int(obs['subject']['reference'].split('/')[-1])
    # … parse pulse, spo2, bp_str …
    _store_and_emit(pid, pulse, spo2, bp_str)
    return jsonify(status="ok"), 201

# MQTT setup (unchanged)
MQTT_BROKER = 'localhost'
MQTT_PORT   = 1883
MQTT_TOPIC  = 'devices/+/vitals'

def _on_connect(client, userdata, flags, rc):
    client.subscribe(MQTT_TOPIC)

def _on_message(client, userdata, msg):
    text = msg.payload.decode()
    print(f"🛰️  MQTT msg on {msg.topic}: {text}")      # ← add this
    try:
        payload = json.loads(text)
        print(f"✅ Parsed payload: {payload}")           # ← and this
        _store_and_emit(
            payload['patient_id'],
            payload['pulse'],
            payload['spo2'],
            payload['bp']
        )
    except Exception as e:
        print("❌ MQTT error:", e)

def start_mqtt():
    client = mqtt.Client()
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(MQTT_BROKER, MQTT_PORT)
    threading.Thread(target=client.loop_forever, daemon=True).start()
    
def _store_and_emit(patient_id, pulse, spo2, bp_str):
    """
    Persist into Postgres *and* broadcast via SSE.
    We import the Flask `app` here so we can push its context.
    """
    # delayed import 
    from BackendAppPMB import app

    # 1) push Flask app context so get_db() works:
    with app.app_context():
        conn = get_db()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO vitals(patient_id,pulse,bp,spo2) "
                    "VALUES (%s,%s,%s,%s) RETURNING timestamp;",
                    (patient_id, pulse, bp_str, spo2)
                )
                ts = cur.fetchone()['timestamp']

    # 2) now broadcast to any connected SSE clients
    msg = json.dumps({
        "id":        patient_id,
        "pulse":     pulse,
        "bp":        bp_str,
        "spo2":      spo2,
        "timestamp": ts.isoformat()
    })
    print(f"📣 Broadcasting to {len(broadcaster.listeners)} client(s): {msg}") 
    broadcaster.broadcast(msg)

def init_app(app):
    # register the Blueprint
    app.register_blueprint(device_bp, url_prefix='/api/devices')
    # start MQTT listener once app is up
    start_mqtt()
