# PMBAppBackEnd.py
import json
import queue
import random
import threading
import time
from flask import Flask, Response, render_template

app = Flask(__name__)

# Event broadcaster to handle Server-Sent Events for multiple clients
class EventBroadcaster:
    def __init__(self):
        self.listeners = []          # List of queues for each client
        self.lock = threading.Lock() # Lock to synchronize access to listeners

    def listen(self):
        """Register a new client and return its queue."""
        q = queue.Queue(maxsize=5)  # each client has its own queue (thread-safe)
        with self.lock:
            self.listeners.append(q)
        return q

    def broadcast(self, message):
        """Put a new message into all client queues. Remove closed connections."""
        with self.lock:
            for q in list(self.listeners):  # iterate over a copy of the list
                try:
                    q.put_nowait(message)   # send message to client queue
                except queue.Full:
                    # If the queue is full, the client might be slow or disconnected.
                    # Remove it to free up resources.
                    self.listeners.remove(q)

broadcaster = EventBroadcaster()

def generate_data():
    """Background thread function to generate random vitals for patients continuously."""
    while True:
        for patient_id in range(1, 6):  # simulate 5 patients with IDs 1-5
            # Generate random vitals
            pulse = random.randint(60, 100)                 # Pulse (bpm)
            systolic = random.randint(110, 140)             # Systolic BP
            diastolic = random.randint(70, 90)              # Diastolic BP
            spo2 = random.randint(90, 100)                  # SpO2 (%)
            data = {
                "id": patient_id,
                "pulse": pulse,
                "bp": f"{systolic}/{diastolic}",
                "spo2": spo2
            }
            # Broadcast the new vitals as a JSON string to all listeners
            broadcaster.broadcast(json.dumps(data))
            time.sleep(1)  # wait 1 second before generating next reading (per patient)

@app.route('/stream')
def stream():
    """SSE endpoint: streams out live vitals data to any client listening."""
    def event_stream():
        # Each client gets a unique Queue to listen for events
        q = broadcaster.listen()
        try:
            # Stream indefinitely until client disconnects
            while True:
                data = q.get()  # block until an event is available
                # Yield the data in SSE format (note the double newline)
                yield f"data: {data}\n\n"
        finally:
            # If the client disconnects, remove its queue from the listeners
            with broadcaster.lock:
                if q in broadcaster.listeners:
                    broadcaster.listeners.remove(q)

    # Return a streaming response with the right content type and no caching
    return Response(event_stream(), content_type='text/event-stream', headers={"Cache-Control": "no-cache"})

@app.route('/')
def index():
    """Serves the main page with patient vitals dashboard."""
    return render_template('index.html')  # index.html will connect to the SSE stream

if __name__ == '__main__':
    # Start the background thread to generate data, as a daemon so it exits on app shutdown
    threading.Thread(target=generate_data, daemon=True).start()
    # Run the Flask development server on port 8080
    app.run(host='0.0.0.0', port=8080)
