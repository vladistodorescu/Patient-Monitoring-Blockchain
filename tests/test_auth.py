# tests/test_auth.py
import os
import sys
import types

# Ensure project root and BackEnd on path
dir_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, dir_root)

import pytest
import json
import time
from flask import Flask, session, request, g

import auth  # this is your auth.py module

@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    # Reset JWKS cache and stub network calls
    auth.jwks_cache['keys'] = None
    auth.jwks_cache['last_updated'] = 0
    # Ensure requests.post/get won't hit real network
    monkeypatch.setattr(auth.requests, 'post', lambda *args, **kwargs: None)
    monkeypatch.setattr(auth.requests, 'get', lambda *args, **kwargs: None)


def test_get_token_from_request_header_and_query():
    app = Flask(__name__)
    with app.test_request_context('/', headers={'Authorization': 'Bearer mytoken'}):
        assert auth.get_token_from_request() == 'mytoken'
    with app.test_request_context('/?access_token=querytoken'):
        assert auth.get_token_from_request() == 'querytoken'
    with app.test_request_context('/'):
        assert auth.get_token_from_request() is None


def test_get_client_credentials_token_success_and_error(monkeypatch):
    # Success
    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {'access_token': 'abc123'}
    monkeypatch.setattr(auth.requests, 'post', lambda url, data: FakeResp())
    token, err = auth.get_client_credentials_token('cid', 'secret', 'scope1')
    assert token == 'abc123'
    assert err is None
    # Error
    class BadResp:
        def raise_for_status(self): raise Exception('error')
    monkeypatch.setattr(auth.requests, 'post', lambda url, data: BadResp())
    token, err = auth.get_client_credentials_token('cid', 'secret')
    assert token is None
    assert 'Error getting client credentials token' in err


def test_get_jwks_caching(monkeypatch):
    # First fetch
    class Resp1:
        def __init__(self): self.status_code = 200
        def raise_for_status(self): pass
        def json(self): return {'keys': [{'kid': 'k1'}]}
    class Resp2(Resp1):
        def json(self): return {'keys': [{'kid': 'k2'}]}
    call = {'count':0}
    def fake_get(url):
        call['count'] += 1
        return Resp1() if call['count']==1 else Resp2()
    monkeypatch.setattr(auth.requests, 'get', fake_get)
    k1 = auth.get_jwks()
    assert k1 == [{'kid':'k1'}]
    # still cached
    keys2 = auth.get_jwks()
    assert keys2 == [{'kid':'k1'}]
    # expire cache
    auth.jwks_cache['last_updated'] = 0
    k2 = auth.get_jwks()
    assert k2 == [{'kid':'k2'}]


def test_handle_callback_success_and_error(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test'
    # Stub token exchange response
    class FakeTokenResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {'access_token':'tok','refresh_token':'r','id_token':'dummy.jwt.token','expires_in':10}
    monkeypatch.setattr(auth.requests, 'post', lambda url, data: FakeTokenResp())
    # Stub jwt.decode to bypass real decoding
    monkeypatch.setattr(auth.jwt, 'decode', lambda token, key=None, options=None, algorithms=None, issuer=None: {'sub':'u1','email':'test@example.com','aud':auth.AUDIENCE,'exp':time.time()+100})

    with app.test_request_context('/callback?code=abc&state=st'):
        session['oauth_state'] = 'st'
        user_info, error = auth.handle_callback('abc', 'st')
        assert error is None
        assert user_info['sub'] == 'u1'

    # State mismatch case
    with app.test_request_context('/callback?code=abc&state=bad'):
        session['oauth_state'] = 'good'
        ui, err = auth.handle_callback('abc', 'bad')
        assert ui is None
        assert err == 'Invalid state parameter'


def test_require_auth_and_require_scope(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test'
    # dummy views
    @auth.require_auth
    def v1(): return 'ok'
    @auth.require_scope('read')
    def v2(): return 'ok2'

    # Stub extraction and verification
    monkeypatch.setattr(auth, 'get_token_from_request', lambda: 'tok')
    monkeypatch.setattr(auth, 'verify_token', lambda t: {'scope':'read write'})

    with app.test_request_context('/', headers={'Authorization':'Bearer tok'}):
        # require_auth
        res1 = v1()
        assert res1 == 'ok'
        # require_scope
        res2 = v2()
        assert res2 == 'ok2'

    # invalid token
    monkeypatch.setattr(auth, 'verify_token', lambda t: None)
    with app.test_request_context('/', headers={'Authorization':'Bearer tok'}):
        resp, code = v1()
        assert code == 401
        resp2, code2 = v2()
        assert code2 == 401

    # missing scope
    monkeypatch.setattr(auth, 'verify_token', lambda t: {'scope':'write'})
    with app.test_request_context('/', headers={'Authorization':'Bearer tok'}):
        _, c = v2()
        assert c == 403
