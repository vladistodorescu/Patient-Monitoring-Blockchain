# DeviceAPI.py V6
import json
import threading
import paho.mqtt.client as mqtt
import os
import time
import json
import signal
import sys



from Blockchain import Blockchain
from flask import Blueprint, request, jsonify
from Database.DatabaseAppPMB import get_db
from Broadcaster import broadcaster
from flask import jsonify

device_bp = Blueprint('device_api', __name__)

# Setup blockchain
blockchain = None

# Define path to backup file
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backup_path = os.path.join(base_dir, 'Database', 'blockchain_backup.json')

# Try to restore blockchain
if os.path.exists(backup_path):
    print("🔄 Blockchain backup found, loading from file...")
    with open(backup_path, 'r') as f:
        data = json.load(f)

    # Rebuild chain
    blockchain = Blockchain()
    blockchain.chain = []

    for block_data in data:
        # Recreate each Block manually
        from Blockchain import Block
        block = Block(
            index=block_data['index'],
            timestamp=block_data['timestamp'],
            data=block_data['data'],
            previous_hash=block_data['previous_hash']
        )
        block.hash = block_data['hash']
        blockchain.chain.append(block)

    print(f"✅ Blockchain restored with {len(blockchain.chain)} blocks!")
else:
    print("🚀 No blockchain backup found, creating new blockchain...")
    blockchain = Blockchain()

def graceful_shutdown(signal, frame):
    print("🛑 Caught shutdown signal! Saving blockchain to file...")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backup_path = os.path.join(base_dir, 'Database', 'blockchain_backup.json')
    with open(backup_path, 'w') as f:
        json.dump(blockchain.to_dict(), f, indent=4)
    print("✅ Blockchain saved successfully. Exiting now.")
    sys.exit(0)

# Attach the signal handler
signal.signal(signal.SIGINT, graceful_shutdown)


@device_bp.route('/fhir', methods=['POST'])
def ingest_fhir_observation():
    obs = request.get_json()
    pid = int(obs['subject']['reference'].split('/')[-1])
    pulse = obs['pulse']
    spo2 = obs['spo2']
    bp_str = obs['bp']
    _store_and_emit(pid, pulse, spo2, bp_str)
    return jsonify(status="ok"), 201

# MQTT setup (unchanged)
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT   = int(os.getenv("MQTT_PORT", "1883"))
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

    # retry until broker is up
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT)
            break
        except ConnectionRefusedError:
            print("❌ MQTT broker not ready, retrying in 1s…")
            time.sleep(1)

    threading.Thread(target=client.loop_forever, daemon=True).start()
    
def _store_and_emit(patient_id, pulse, spo2, bp_str):
    """
    Persist into Postgres *and* broadcast via SSE.
    We import the Flask `app` here so we can push its context.
    """
    # delayed import to avoid circular dependency at module load time
    from PMBAppBackEnd import app


    # 1) push the Flask app context so get_db() (which uses flask.g) works:
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

    blockchain.add_block({
    "patient_id": patient_id,
    "pulse": pulse,
    "bp": bp_str,
    "spo2": spo2,
    "timestamp": time.time()
    })
    print(f"✅ Block added! Current blockchain length: {len(blockchain.chain)}")#comment this later
    print(f"Last block: {blockchain.chain[-1].__dict__}")#this too

    # Save blockchain to file after every new block
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_folder = os.path.join(base_dir, "Database")
    if not os.path.exists(db_folder):
        os.makedirs(db_folder)

    # Now save blockchain correctly
    with open(os.path.join(db_folder, 'blockchain_backup.json'), 'w') as f:
        json.dump(blockchain.to_dict(), f, indent=4)
    print(f"📣 Broadcasting to {len(broadcaster.listeners)} client(s): {msg}") 
    broadcaster.broadcast(msg)

@device_bp.route('/blockchain', methods=['GET'])
def get_blockchain():
    chain_data = blockchain.to_dict()
    return jsonify(chain_data), 200

def init_app(app):
    # register the Blueprint
    app.register_blueprint(device_bp, url_prefix='/api/devices')
    # start MQTT listener once app is up
    start_mqtt()
