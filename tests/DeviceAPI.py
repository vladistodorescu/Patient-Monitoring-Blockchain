# tests/test_DeviceAPI.py
import os
import sys
import types

# Ensure project root and BackEnd on path
dir_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, dir_root)
sys.path.insert(0, os.path.join(dir_root, 'BackEnd'))

# Stub out external modules before importing
sys.modules['hfc'] = types.ModuleType('hfc')
sys.modules['hfc.fabric'] = types.ModuleType('hfc.fabric')
setattr(sys.modules['hfc.fabric'], 'Client', lambda *args, **kwargs: None)

fake_blockchain_module = types.ModuleType('Blockchain')
fake_blockchain = types.SimpleNamespace(record_vitals=lambda *args, **kwargs: None)
setattr(fake_blockchain_module, 'blockchain', fake_blockchain)
sys.modules['Blockchain'] = fake_blockchain_module

import pytest
import json
from flask import Flask, g

import DeviceAPI as api

@pytest.fixture(autouse=True)
def disable_dependencies(monkeypatch):
    # Prevent MQTT subscriber thread
    monkeypatch.setattr(api, 'start_mqtt', lambda: None)

# -- Tests --

def test_ingest_fhir_observation(monkeypatch):
    """
    Test the /api/devices/fhir endpoint logic by calling the core view function directly.
    """
    calls = []
    # Stub storage logic
    monkeypatch.setattr(api, '_store_and_emit', lambda pid, pulse, spo2, bp, uid, cid: calls.append((pid, pulse, spo2, bp, uid, cid)))

    app = Flask(__name__)
    payload = {'subject': {'reference': 'Patient/15'}, 'pulse': 66, 'spo2': 98, 'bp': '117/75'}

    # Use the undecorated view function (__wrapped__ twice for two decorators)
    view_fn = api.ingest_fhir_observation.__wrapped__.__wrapped__

    with app.test_request_context(json=payload):
        g.user = {'sub': 'userX', 'azp': 'clientX'}
        resp, code = view_fn()

    assert code == 201
    assert resp.get_json() == {'status': 'ok'}
    assert calls == [(15, 66, 98, '117/75', 'userX', 'clientX')]


def test_on_connect_and_subscribe(capsys):
    """
    _on_connect should subscribe on success and log appropriately.
    """
    class DummyClient:
        def __init__(self): self.topic = None
        def subscribe(self, topic): self.topic = topic

    client = DummyClient()
    api._on_connect(client, None, None, 0)
    out = capsys.readouterr().out
    assert 'MQTT connected' in out
    assert client.topic == api.MQTT_TOPIC

    client = DummyClient()
    api._on_connect(client, None, None, 1)
    out = capsys.readouterr().out
    assert 'connection failed' in out.lower()
    assert client.topic is None


def test_on_message_authenticated(monkeypatch):
    """
    Authenticated MQTT payload should parse and call storage logic.
    """
    data = {'patient_id': 3, 'pulse': 70, 'spo2': 99, 'bp_systolic': 110, 'bp_diastolic': 70}
    payload = {'data': data, 'token': 'tok'}
    msg = type('M', (), {'topic': 'devices/3/vitals', 'payload': json.dumps(payload).encode()})()

    # Stub token verification and capture logic
    monkeypatch.setattr(api, 'verify_token', lambda t: {'sub': 'u2', 'azp': 'c2', 'scope': 'write:vitals mqtt:publish'})
    stored = []
    monkeypatch.setattr(api, '_store_and_emit', lambda *args, **kwargs: stored.append(args))

    api._on_message(None, None, msg)
    assert stored == [(3, 70, 99, '110/70', 'u2', 'c2')]


def test_on_message_legacy(monkeypatch):
    """
    Legacy MQTT payload (no token) should default to 'legacy' auth.
    """
    data = {'patient_id': 4, 'pulse': 80, 'spo2': 95, 'bp_systolic': 120, 'bp_diastolic': 80}
    msg = type('M', (), {'topic': 'devices/4/vitals', 'payload': json.dumps(data).encode()})()

    monkeypatch.setattr(api, 'verify_token', lambda t: None)
    stored = []
    monkeypatch.setattr(api, '_store_and_emit', lambda *args, **kwargs: stored.append(args))

    api._on_message(None, None, msg)
    assert stored == [(4, 80, 95, '120/80', 'legacy', 'legacy')]
