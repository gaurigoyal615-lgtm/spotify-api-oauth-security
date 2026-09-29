import os
import secrets
from urllib.parse import urlencode
from flask import Flask, redirect, request, session, abort
from dotenv import load_dotenv
import string,hashlib,base64
from flask_session import Session
load_dotenv()
app = Flask(__name__)

app.config["SESSION_PERMANENT"] = False     # Sessions expire when browser closes
app.config["SESSION_TYPE"] = "filesystem"     # Store session data on the filesystem
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]
Session(app)


AUTH_PROVIDER_URL = "https://accounts.spotify.com/authorize"      #  |- I am fetching it from .env which is hidden on github(cause it's personal duh ;) )

#Flask knowledge: app.config stores application-wide settings as dict
#A Flask session stores user-specific data across requests, like login status, using cookies 
#Saving data for use throughout a session allows the web app to keep data persistent over multiple requests -- i.e., as a user accesses different pages within a web app.
#by default Flask uses client-side sessions but we want to store sensitive data so we want server-side session
CLIENT_ID= app.config['SPOTIFY_CLIENT_ID'] = os.environ['SPOTIFY_CLIENT_ID'] #client id given by spotify itself when I initiated an app from their website

def generate_secure_string(length=64):  # to generate client_verifier which is secret generated for this PKCE auth transaction
    
    # Combines letters and numbers: abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
    
    characters = string.ascii_letters + string.digits       
    return ''.join(secrets.choice(characters) for _ in range(length))

    
@app.route('/login') 

def login():
    state = secrets.token_urlsafe(32) #creating a state for user session which has to be stored so that the server can handle multiple same type of request uniquely
    
    session['oauth_state'] = state #have to store that state so that the response can match it with its state
    
    code_verifier = generate_secure_string(64)
    session['code_verifier']= code_verifier
    
    hashed = hashlib.sha256(code_verifier.encode('utf-8')).digest() # created an hash of the generated random string            |
                                                #   |
    codeChallenge = base64.urlsafe_b64encode(hashed).rstrip(b"=").decode("ascii") # converted that hash to base64 encoding       |- convention to make a codechallenge -> its the method which will be sent to the server rather than the code_verifer itself
    
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "state": state,                                             # these are the final parametes which our request will carry with itself to the server
        "code_challenge_method": 'S256',
        "code_challenge": codeChallenge,
        "redirect_uri": "http://127.0.0.1:5000/callback",
        "scope": "user-top-read user-read-recently-played"
        
        
    }
    return redirect(f"{AUTH_PROVIDER_URL}?{urlencode(params)}")         

if __name__ == '__main__':
    app.run(debug=True)