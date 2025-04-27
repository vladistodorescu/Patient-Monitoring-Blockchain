import time
import json
import random
import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
NUM_PATIENTS = 5
PUBLISH_INTERVAL = 5  # seconds

client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT)

print("🔄 Starting MQTT simulator for 5 patients...")

while True:
    for patient_id in range(1, NUM_PATIENTS + 1):
        # 🔥 Generează random la fiecare ciclu!
        pulse = random.randint(55, 110)  # Pulse between 55-110 bpm
        spo2 = random.randint(85, 100)   # SpO2 between 85%-100%
        bp_sys = random.randint(100, 160)  # Systolic BP
        bp_dia = random.randint(60, 100)   # Diastolic BP
        
        payload = {
            "patient_id": patient_id,
            "pulse": pulse,
            "spo2": spo2,
            "bp": f"{bp_sys}/{bp_dia}"
        }
        
        topic = f"devices/patient{patient_id}/vitals"
        client.publish(topic, json.dumps(payload))
        
        print(f"📤 Published to {topic}: {payload}")
    
    time.sleep(PUBLISH_INTERVAL)
