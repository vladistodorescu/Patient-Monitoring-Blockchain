# Back End/Blockchain.py
import json
import os
import asyncio
from dotenv import load_dotenv 
from hfc.fabric import Client

load_dotenv()

class FabricClient:
    def __init__(self):
        # 1) Read JSON Connection
        cfg_path = os.getenv('FABRIC_NETWORK_CONFIG')
        with open(cfg_path, 'r') as f:
            conn_profile = json.load(f)
            
        # 2) Pull out exactly what you need 
        self.channel = os.getenv('FABRIC_CHANNEL_NAME', 'mychannel')
        self.cc_name = os.getenv('FABRIC_CHAINCODE_NAME')
        org = os.getenv('FABRIC_ORG')
        user = os.getenv('FABRIC_USER')
        self.peers = conn_profile['organizations'][org]['peers']
        
        # 3) Then initialize the SDK as before (it will re-re-load the same file)
        self.client = Client(net_profile=cfg_path)
        self.client.new_channel(self.channel)
        self.user = self.client.get_user(org, user)
        

    def _invoke(self, fcn, args):
        return self.client.chaincode_invoke(
            requestor=self.user,
            channel_name=self.channel,
            peers=self.peers,
            cc_name=self.cc_name,
            fcn=fcn,
            args=args,
            wait_for_event=True
        )

    def record_vitals(self, patient_id, pulse, bp, spo2, timestamp):
        """
        Submits a RecordVitals transaction to the Fabric network.
        """
        args = [str(patient_id), str(pulse), bp, str(spo2), timestamp]
        return self._invoke('RecordVitals', args)
        

# Expose a singleton for easy import
blockchain = FabricClient()
