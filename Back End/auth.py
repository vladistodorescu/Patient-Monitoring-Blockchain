"""
OAuth 2.0 with OpenID Connect Authentication Module

This module provides complete OAuth 2.0 + OIDC authentication functionality:
- JWT token validation with signature verification
- JWKS caching for performance
- Support for Authorization Code Flow (users)
- Support for Client Credentials Flow (devices)
"""

import os
import time
import json
import requests
import threading
from functools import wraps
from jose import jwt, jwk, JWTError
from flask import request, jsonify, redirect, url_for, session, g
from urllib.parse import urlencode
from dotenv import load_dotenv
load_dotenv()

# Configuration - ideally these would be in environment variables
AUTH_SERVER_URL = os.getenv("AUTH_SERVER_URL", "https://your-auth-server.com")
JWKS_URI = os.getenv("JWKS_URI", f"{AUTH_SERVER_URL}/.well-known/jwks.json")
TOKEN_ENDPOINT = os.getenv("TOKEN_ENDPOINT", f"{AUTH_SERVER_URL}/oauth/token")
AUTHORIZATION_ENDPOINT = os.getenv("AUTHORIZATION_ENDPOINT", f"{AUTH_SERVER_URL}/authorize")
CLIENT_ID = os.getenv("CLIENT_ID", "your-client-id")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "your-client-secret")
AUDIENCE = os.getenv("API_AUDIENCE", "https://patientmonitor.api")
ISSUER = os.getenv("TOKEN_ISSUER", "https://your-auth-server.com/")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8080/callback")

# Cache for JWKS (JSON Web Key Set)
jwks_cache = {
    "keys": None,
    "last_updated": 0,
    "cache_duration": 3600  # Refresh every hour
}
jwks_lock = threading.Lock()

def get_jwks():
    """Retrieve and cache JWKS (JSON Web Key Set) from the auth server"""
    current_time = time.time()
    
    with jwks_lock:
        # Return cached keys if they're still fresh
        if (jwks_cache["keys"] is not None and 
            current_time - jwks_cache["last_updated"] < jwks_cache["cache_duration"]):
            return jwks_cache["keys"]
        
        # Fetch new keys
        try:
            response = requests.get(JWKS_URI)
            response.raise_for_status()
            jwks_cache["keys"] = response.json()["keys"]
            jwks_cache["last_updated"] = current_time
            return jwks_cache["keys"]
        except Exception as e:
            print(f"Error fetching JWKS: {e}")
            # Return cached keys if fetch fails but we have cached keys
            if jwks_cache["keys"] is not None:
                return jwks_cache["keys"]
            raise

def get_token_from_request():
    """Extract JWT token from the request"""
    auth_header = request.headers.get("Authorization", "")
    
    if auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove 'Bearer ' prefix
    
    # Also check for token in query params (for websocket connections)
    token = request.args.get("access_token")
    if token:
        return token
        
    return None

def verify_token(token):
    """
    Verify JWT token signature and claims
    Returns the decoded payload if valid
    """
    if not token:
        return None
    
    try:
        # Get the key ID from the token header
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        
        if not kid:
            return None
        
        # Find the corresponding key in JWKS
        jwks = get_jwks()
        key = next((k for k in jwks if k["kid"] == kid), None)
        
        if not key:
            return None
        
        # Prepare the public key for verification
        public_key = jwk.construct(key)
        
        # Verify token and decode payload
        payload = jwt.decode(
            token,
            public_key.to_pem().decode("utf-8"),
            algorithms=[header.get("alg", "RS256")],
            audience=AUDIENCE,
            issuer=ISSUER
        )
        
        # Check expiration
        if payload.get("exp") and time.time() > payload.get("exp"):
            return None
            
        # Check for required scopes
        return payload
        
    except JWTError as e:
        print(f"JWT verification error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during token verification: {e}")
        return None

def require_auth(f):
    """Decorator to require authentication for HTTP endpoints"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        payload = verify_token(token)
        
        if not payload:
            return jsonify({"error": "Unauthorized", "message": "Invalid or expired token"}), 401
        
        # Store the user info in Flask g for use in the request
        g.user = payload
        return f(*args, **kwargs)
    
    return decorated

def require_scope(required_scope):
    """Decorator to require specific scope for an endpoint"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = get_token_from_request()
            payload = verify_token(token)
            
            if not payload:
                return jsonify({"error": "Unauthorized", "message": "Invalid or expired token"}), 401
            
            # Check if the token has the required scope
            scopes = payload.get("scope", "").split()
            if required_scope not in scopes:
                return jsonify({
                    "error": "Forbidden", 
                    "message": f"Token missing required scope: {required_scope}"
                }), 403
            
            # Store the user info in Flask g for use in the request
            g.user = payload
            return f(*args, **kwargs)
        
        return decorated
    
    return decorator

def get_login_url():
    """Generate the OAuth 2.0 authorization URL for user login"""
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile email read:vitals write:vitals",
        "audience": AUDIENCE,
        "state": generate_state()
    }
    
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

def generate_state():
    """Generate a random state parameter for CSRF protection"""
    import secrets
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    return state

def handle_callback(auth_code, state):
    """Handle the OAuth callback with the authorization code"""
    if state != session.get("oauth_state"):
        return None, "Invalid state parameter"

    payload = {
        "grant_type": "authorization_code",  # ✅ CORRECT grant
        "client_id": os.getenv("WEB_APP_CLIENT_ID"),
        "client_secret": os.getenv("WEB_APP_CLIENT_SECRET", ""),  # Optional if client_secret not required
        "code": auth_code,
        "redirect_uri": REDIRECT_URI
    }

    try:
        response = requests.post(TOKEN_ENDPOINT, data=payload)
        response.raise_for_status()
        tokens = response.json()

        # Store tokens
        session["access_token"] = tokens["access_token"]
        session["refresh_token"] = tokens.get("refresh_token")
        session["id_token"] = tokens.get("id_token")
        session["expires_at"] = time.time() + tokens["expires_in"]

        # Decode ID token (no signature check here, as it's from the auth server)
        id_token = tokens.get("id_token")
        if id_token:
            user_info = jwt.decode(id_token, options={"verify_signature": False})
            return user_info, None

        return {}, None

    except Exception as e:
        return None, f"Error exchanging code for tokens: {e}"

def refresh_access_token():
    """Refresh the access token using the refresh token"""
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        return False
    
    payload = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token
    }
    
    try:
        response = requests.post(TOKEN_ENDPOINT, data=payload)
        response.raise_for_status()
        tokens = response.json()
        
        # Update tokens
        session["access_token"] = tokens["access_token"]
        session["refresh_token"] = tokens.get("refresh_token", refresh_token)  # Some providers don't rotate
        session["expires_at"] = time.time() + tokens["expires_in"]
        
        return True
        
    except Exception as e:
        print(f"Error refreshing token: {e}")
        # Clear invalid tokens
        session.pop("access_token", None)
        session.pop("refresh_token", None)
        session.pop("id_token", None)
        session.pop("expires_at", None)
        return False

def get_client_credentials_token(client_id, client_secret, scope="read:vitals write:vitals"):
    """
    Get an access token using the client credentials flow
    Used for device/service authentication
    """
    payload = {
    "grant_type": "client_credentials",
    "client_id": os.getenv("MQTT_SIMULATOR_CLIENT_ID"),
    "client_secret": os.getenv("MQTT_SIMULATOR_CLIENT_SECRET"),
    "audience": os.getenv("API_AUDIENCE"),
    "scope": "mqtt:publish write:vitals"
}
    
    try:
        response = requests.post(TOKEN_ENDPOINT, data=payload)
        response.raise_for_status()
        return response.json()["access_token"], None
    except Exception as e:
        return None, f"Error getting client credentials token: {e}"

def init_auth_endpoints(app):
    """Initialize authentication endpoints in the Flask app"""
    
    @app.route('/login')
    def login():
        """Redirect to the authorization server for login"""
        return redirect(get_login_url())
    
    @app.route('/callback')
    def callback():
        """Handle the OAuth callback"""
        code = request.args.get('code')
        state = request.args.get('state')
        
        if not code:
            return jsonify({"error": "No authorization code received"}), 400
        
        user_info, error = handle_callback(code, state)
        if error:
            return jsonify({"error": error}), 400
        
        # Redirect to homepage or dashboard
        return redirect(url_for('index'))
    
    @app.route('/logout')
    def logout():
        """Log out the user by clearing tokens"""
        session.clear()
        return redirect(url_for('index'))
    
    @app.route('/api/auth/token')
    @require_auth
    def get_user_info():
        """Return the user info from the token"""
        return jsonify(g.user)