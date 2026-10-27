import os
import secrets
from urllib.parse import urlencode
from flask import Flask, redirect, request, session, abort
from dotenv import load_dotenv
import string,hashlib,base64
from flask_session import Session
import redis
import requests
import time
load_dotenv()
app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]  #  |- I am fetching it from .env which is hidden on github(cause it's personal duh ;) )

#Flask knowledge: app.config stores application-wide settings as dict
#A Flask session stores user-specific data across requests, like login status, using cookies 
#Saving data for use throughout a session allows the web app to keep data persistent over multiple requests -- i.e., as a user accesses different pages within a web app.
#by default Flask uses client-side sessions but we want to store sensitive data so we want server-side session

app.config["SESSION_TYPE"] = "redis"     # Store session data on redis
app.config["SESSION_PERMANENT"] = False     # Sessions expire when browser closes
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_REDIS'] = redis.from_url('redis://127.0.0.1:6379')


Session(app) # initializes the Flask-Session integration


AUTH_PROVIDER_URL = "https://accounts.spotify.com/authorize"     


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
    
    hashed = hashlib.sha256(code_verifier.encode('utf-8')).digest() # created an hash of the generated random string            |                                           #   |
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
    authorization_url = f"{AUTH_PROVIDER_URL}?{urlencode(params)}" 
    return redirect(authorization_url)  

TOKEN_URL = "https://accounts.spotify.com/api/token"
REDIRECT_URI = "http://127.0.0.1:5000/callback"

@app.route('/callback')
def callback():
    #read the values spotify returned
    returned_state = request.args.get("state")
    code = request.args.get("code")
    error = request.args.get("error")

    # retreive the state saves during /login
    saved_state = session.get("oauth_state")
    
    if (
        not returned_state
        or not saved_state
        or not secrets.compare_digest(returned_state, saved_state)
    ):
        session.pop("oauth_state", None)
        session.pop("code_verifier", None)
        abort(400, description= "Invalid OAuth state. Please try logging in again.")

        # retreive the PKCE verifier saved during /login
    code_verifier = session.get("code_verifier")
        
        #this auth attempt has now been checked.
        #remove its temp values to prevent reuse.
    session.pop("oauth_state", None)
    session.pop("code_verifier", None)
        
        # Handle the user denying auth
    if error:
            return f"Spotify authorization failed: {error}", 400
        
        # check that Spotify retuerned an auth code
    if not code or not code_verifier:
            abort(400, description= "Missing authorization code or PKCE verifier.")
        
    #Exchange the code for tokens
       
    token_data = {
        "client_id": CLIENT_ID,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier
    }
    
    try:
        response = requests.post(
             TOKEN_URL,
             data=token_data,
             timeout=15
        )
        response.raise_for_status()
        tokens = response.json()
    
    except requests.RequestException:
        app.logger.exception("Spotify token rquest failed.")
        return "Token exchange failed. Check the Flask logs.", 502
    
    # store tokens in the server-side session
    session["access_token"] = tokens["access_token"]
    session["expires_at"] = time.time() + tokens["expires_in"]
    
    
    
    if tokens.get("refresh_token"):
        session["refresh_token"] = tokens["refresh_token"]
    
    
    # Confirm success w/o displaying any tokens
    return "Spotify authorization successful! Tokens stored server-side."


#this route is giving all the info about the authenticated user

@app.route('/me')
def me():
    response, error = spotify_api_request("me")

    if error == "not_authenticated":
        return redirect("/login")

    if error == "refresh_failed":
        return "Token refresh failed. Please log in again.", 401

    if error == "request_failed":
        return "Could not reach Spotify. Try again later.", 502

    if response.status_code == 401:
        return "Spotify rejected the access token.", 401

    if not response.ok:
        app.logger.warning(
            "Spotify profile request returned HTTP %s",
            response.status_code
        )
        return "Spotify profile request failed.", 502

    profile = response.json()

    return {
        "display_name": profile.get("display_name"),
        "id": profile.get("id"),
        "spotify_url": profile.get("external_urls", {}).get("spotify")
    }

    
    # An access token is a short-lived credential used to access protected resources and APIs, while a refresh token is a long-lived credential used exclusively to request a new access token when the old one expires
        
    # Our goal is to make your app check the access token's expiry before calling the API and refresh it when necessary.
      
def refresh_access_token():
    refresh_token = session.get("refresh_token")
    
    if not refresh_token:
        return False
    
    refresh_data = {
        "grant_type": "refresh_token" , # grant_type="refresh_token" tells   Spotify which OAuth operation we're performing
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID
    }
    
    try:
        response = requests.post(
            TOKEN_URL,
            data=refresh_data,
            timeout=15
        )
        if response.status_code == 400:
            error_data = response.json()
            if error_data.get("error") == "invalid_grant":
                session.pop("access_token", None)
                session.pop("refresh_token", None)
                session.pop("expires_at", None)
                return False
            
        response.raise_for_status()
        tokens = response.json()
        
    except requests.RequestException:
        app.logger.exception("Spotify token refresh failed")
        return False
    
    session["access_token"] = tokens["access_token"]
    session["expires_at"] = time.time() + tokens["expires_in"]
    
    # Spotify may not return a replacement refresh token.
    if tokens.get("refresh_token"):
        session["refresh_token"] = tokens["refresh_token"]

    app.logger.info("Spotify access token refreshed successfully")
    
    return True


def spotify_api_request(endpoint, params=None):
    access_token = session.get("access_token")
    expires_at = session.get("expires_at")

    if not access_token or not expires_at:
        return None, "not_authenticated"

    if time.time() >= expires_at - 60:
        if not refresh_access_token():
            return None, "refresh_failed"

        access_token = session.get("access_token")

    try:
        response = requests.get(
            f"https://api.spotify.com/v1/{endpoint.lstrip('/')}",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15
        )
        return response, None

    except requests.RequestException:
        app.logger.exception("Spotify API request failed")
        return None, "request_failed"


@app.route('/top/artists')
def top_artists():
    response, error = spotify_api_request(
        "me/top/artists",
        params={"limit": 10, "time_range": "medium_term"}
    )

    if error == "not_authenticated":
        return redirect("/login")

    if error == "refresh_failed":
        return "Token refresh failed. Please log in again.", 401

    if error == "request_failed":
        return "Could not reach Spotify. Try again later.", 502

    if not response.ok:
        app.logger.warning(
            "Top artists request returned HTTP %s",
            response.status_code
        )
        return "Could not fetch top artists.", response.status_code

    artists = response.json()["items"]

    return {
        "top_artists": [
            {
                "name": artist["name"],
                "id": artist["id"],
                "spotify_url": artist["external_urls"]["spotify"]
            }
            for artist in artists
        ]
    }


@app.route('/top/tracks')
def top_tracks():
    response, error = spotify_api_request(
        "me/top/tracks",
        params={"limit": 10, "time_range": "medium_term"}
    )

    if error == "not_authenticated":
        return redirect("/login")

    if error == "refresh_failed":
        return "Token refresh failed. Please log in again.", 401

    if error == "request_failed":
        return "Could not reach Spotify. Try again later.", 502

    if not response.ok:
        app.logger.warning(
            "Top tracks request returned HTTP %s",
            response.status_code
        )
        return "Could not fetch top tracks.", response.status_code

    tracks = response.json()["items"]

    return {
        "top_tracks": [
            {
                "name": track["name"],
                "id": track["id"],
                "artists": [
                    artist["name"] for artist in track["artists"]
                ],
                "spotify_url": track["external_urls"]["spotify"]
            }
            for track in tracks
        ]
    }
   
if __name__ == '__main__':
    app.run(debug=True)