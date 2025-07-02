# tests/test_Blockchain.py
import os
import sys
import json
tempfile = __import__('tempfile')
import pytest
import types
import importlib.util

# --- Prepare environment & stubs ---
# Create a dummy Fabric network config JSON file
cfg_profile = {'organizations': {'OrgX': {'peers': ['peer1']}}}
tmp_cfg = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
tmp_cfg.write(json.dumps(cfg_profile).encode())
tmp_cfg.flush()
# Set required env vars
os.environ['FABRIC_NETWORK_CONFIG'] = tmp_cfg.name
os.environ['FABRIC_CHANNEL_NAME'] = 'chan'
os.environ['FABRIC_CHAINCODE_NAME'] = 'ccname'
os.environ['FABRIC_ORG'] = 'OrgX'
os.environ['FABRIC_USER'] = 'UserY'
# Stub out hfc.fabric.Client
sys.modules['hfc'] = types.ModuleType('hfc')
sys.modules['hfc.fabric'] = types.ModuleType('hfc.fabric')
class DummyClient:
    def __init__(self, net_profile):
        self.net_profile = net_profile
        self.created_channel = None
        self.user = None
    def new_channel(self, channel):
        self.created_channel = channel
    def get_user(self, org, user):
        return (org, user)
    def chaincode_invoke(self, requestor, channel_name, peers, cc_name, fcn, args, wait_for_event):
        return {
            'requestor': requestor,
            'channel_name': channel_name,
            'peers': peers,
            'cc_name': cc_name,
            'fcn': fcn,
            'args': args,
            'wait_for_event': wait_for_event
        }
setattr(sys.modules['hfc.fabric'], 'Client', DummyClient)

# --- Dynamically load BackEnd/Blockchain.py as module 'blockchain_mod' ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
blockchain_path = os.path.join(project_root, 'BackEnd', 'Blockchain.py')
spec = importlib.util.spec_from_file_location('blockchain_mod', blockchain_path)
blockchain_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blockchain_mod)

# --- Tests ---
def test_fabric_client_singleton_and_attributes():
    # The module-level singleton should be instantiated
    inst = getattr(blockchain_mod, 'blockchain', None)
    assert inst is not None
    # Check that attributes match environment
    assert inst.channel == 'chan'
    assert inst.cc_name == 'ccname'
    assert inst.peers == ['peer1']
    # Client should be DummyClient
    assert isinstance(inst.client, DummyClient)
    assert inst.client.net_profile == tmp_cfg.name
    assert inst.client.created_channel == 'chan'
    assert inst.user == ('OrgX', 'UserY')


def test_record_vitals_invocation():
    inst = getattr(blockchain_mod, 'blockchain')
    # Call record_vitals and verify payload
    result = inst.record_vitals(
        patient_id=7,
        pulse=65,
        bp='110/70',
        spo2=98,
        timestamp='time123'
    )
    assert result['requestor'] == ('OrgX', 'UserY')
    assert result['channel_name'] == 'chan'
    assert result['peers'] == ['peer1']
    assert result['cc_name'] == 'ccname'
    assert result['fcn'] == 'RecordVitals'
    assert result['args'] == ['7', '65', '110/70', '98', 'time123']
    assert result['wait_for_event'] is True
