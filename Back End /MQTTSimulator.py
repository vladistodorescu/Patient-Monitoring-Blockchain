# MQTTSimulator.py for V5
import time
import random
import json
import paho.mqtt.publish as publish

BROKER   = "localhost"
PORT     = 1883
TOPIC_TMPL = "devices/patient{}/vitals"

NUM_PATIENTS = 5
INTERVAL_SEC = 2   # wait 2 seconds between full rounds

def gen_reading(pid):
    return {
        "patient_id": pid,
        "pulse":      random.randint(60, 100),
        "spo2":       random.randint(90, 100),
        "bp":         f"{random.randint(110,140)}/{random.randint(70,90)}"
    }

def main():
    print(f"🔄 Starting MQTT simulator for {NUM_PATIENTS} patients...")
    for pid in range(1, NUM_PATIENTS+1):
        reading = gen_reading(pid)
        topic = TOPIC_TMPL.format(pid)
        payload = json.dumps(reading)
        publish.single(topic, payload, hostname=BROKER, port=PORT)
        print(f"📤 Published to {topic}: {payload}")
        time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    main()
