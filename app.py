import os
import secrets
from urllib.parse import urlencode
from flask import Flask, redirect, request, session, abort
from dotenv import load_dotenv
import string,hashlib,base64
load_dotenv()
app = Flask(__name__)

app.secret_key = secrets.token_hex(32)

AUTH_PROVIDER_URL = "https://accounts.spotify.com/authorize"
CLIENT_ID= app.config['SPOTIFY_CLIENT_ID'] = os.environ['SPOTIFY_CLIENT_ID']
def generate_secure_string(length=16):
    # Combines letters and numbers: abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

    
@app.route('/login')

def login():
    state = secrets.token_urlsafe(32)
    
    session['oauth_state'] = state
    code_verifier = generate_secure_string(64)
    session['code_verifier']= code_verifier
    hashed = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    codeChallenge = base64.urlsafe_b64decode(hashed).rstrip(b"=").decode("ascii")
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "state": state,
        "code_challenge_method": 'S256',
        "code_challenge": codeChallenge,
        "redirect_uri": "http://127.0.0.1:5000/callback",
        "scope": "user-top-read user-read-recently-played"
        
        
    }
    return redirect(f"{AUTH_PROVIDER_URL}?{urlencode(params)}")

if __name__ == '__main__':
    app.run(debug=True)