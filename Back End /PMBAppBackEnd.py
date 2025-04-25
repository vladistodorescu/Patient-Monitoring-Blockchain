#BackendPMBApp.py
import json
import queue
import random
import threading
import time

from flask import Flask, Response, render_template, jsonify
from DatabaseAppPMB import get_db, close_db, init_db
from DeviceAPI import device_bp        # your device‐integration Blueprint
from Broadcaster import broadcaster    # the shared EventBroadcaster instance

app = Flask(__name__)
app.teardown_appcontext(close_db)

# 1) Register the device‐integration routes on /api/devices
app.register_blueprint(device_bp, url_prefix='/api/devices')

# 2) SSE endpoint: clients connect here to receive live JSON messages
@app.route('/stream')
def stream():
    def event_stream():
        q = broadcaster.listen()
        try:
            while True:
                msg = q.get()                     # block until new message
                yield f"data: {msg}\n\n"          # SSE format
        finally:
            # on client disconnect, remove its queue
            with broadcaster.lock:
                if q in broadcaster.listeners:
                    broadcaster.listeners.remove(q)

    return Response(
        event_stream(),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache'}
    )

# 3) Optional: return the full history of vitals readings
@app.route('/vitals', methods=['GET'])
def get_vitals():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT patient_id AS id, timestamp, pulse, bp, spo2
              FROM vitals
             ORDER BY timestamp;
        """)
        rows = cur.fetchall()
    return jsonify(rows)

# 4) Dashboard page
@app.route('/')
def index():
    return render_template('index.html')

# 5) Simulator to generate data if no real devices are hooked up
def simulate_loop():
    with app.app_context():
        while True:
            for pid in range(1, 6):
                pulse = random.randint(60, 100)
                sys   = random.randint(110, 140)
                dia   = random.randint(70,  90)
                spo2  = random.randint(90, 100)
                bp    = f"{sys}/{dia}"

                # store in DB and get timestamp
                conn = get_db()
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO vitals(patient_id,pulse,bp,spo2) "
                            "VALUES (%s,%s,%s,%s) RETURNING timestamp;",
                            (pid, pulse, bp, spo2)
                        )
                        ts = cur.fetchone()['timestamp']

                # broadcast to all SSE clients
                payload = json.dumps({
                    "id":        pid,
                    "pulse":     pulse,
                    "bp":        bp,
                    "spo2":      spo2,
                    "timestamp": ts.isoformat()
                })
                broadcaster.broadcast(payload)
                time.sleep(1)

if __name__ == '__main__':
    # Initialize DB and seed patients
    with app.app_context():
        init_db()

    # Start simulator (comment out if using real device ingestion only)
    threading.Thread(target=simulate_loop, daemon=True).start()

    # Run on port 8080, listening on all interfaces
    app.run(host='0.0.0.0', port=8080)

