# mocking: not depending on actual servwers for the response data
# this makes testing fast
# hence we add mock spotify_api_request() and return a fake response
# this test does not prove that Spotify login or token refresh works. It isolates the route's behavior: given a successful helper response, does the route return the correct JSON?

from unittest.mock import patch, Mock

import app
import time
from flask import session, Flask, request
import requests

def test_top_artists_returns_artist_data():
    # Create fake Spotify data
    fake_data = {
        "items": [
            {
                "name": "Test Artist",
                "id": "artist123",
                "external_urls": {
                    "spotify": "https://open.spotify.com/artist/artist123"
                }
            }
        ]
    }

    # Pretend Spotify returned a successful response
    fake_response = Mock()
    fake_response.ok = True
    fake_response.json.return_value = fake_data

    # Replace the helper with our fake response
    with patch(
        "app.spotify_api_request",
        return_value=(fake_response, None)
    ): #temporarily replaces real helper with a fake one
        
        # Send a request to our Flask route
        client = app.app.test_client() # lets us send requests to Flask without starting a server or opening a browser.
        response = client.get("/top/artists")

    # Check the result
    assert response.status_code == 200

    result = response.get_json()
    assert result["top_artists"][0]["name"] == "Test Artist"
    assert result["top_artists"][0]["id"] == "artist123"
    assert result["top_artists"][0]["spotify_url"] == (
        "https://open.spotify.com/artist/artist123"
    )


def test_top_artists_redirects_when_not_authenticated():
    with patch(
        "app.spotify_api_request",
        return_value=(None, "not_authenticated")
    ):
        client = app.app.test_client()
        response = client.get("/top/artists")

    assert response.status_code == 302
    assert response.location.endswith("/login")



def test_top_artists_handles_spotify_api_error():
    fake_response = Mock()
    fake_response.ok = False
    fake_response.status_code = 403

    with patch(
        "app.spotify_api_request",
        return_value=(fake_response, None)
    ):
        client = app.app.test_client()
        response = client.get("/top/artists")

    assert response.status_code == 403
    assert response.get_data(as_text=True) == (
        "Could not fetch top artists."
    )


def test_spotify_api_request_without_token():
    from app import spotify_api_request

    with app.app.test_request_context("/"):
        session.clear()

        result, error = spotify_api_request("me")

        assert result is None
        assert error == "not_authenticated"


#now we are testing that given a refresh token in the session and a successful response from Spotify, does refresh_access_token() save the new access token and expiry correctly?

def test_refresh_access_token_success(monkeypatch):
    import time

    with app.app.test_request_context("/"):
        # Arrange: simulate an existing refresh token
        session["refresh_token"] = "old_refresh_token"

        # Simulate Spotify successfully returning a new access token
        class FakeResponse:
            ok = True
            status_code = 200
            def raise_for_status(self):
                    pass 
            def json(self):
                return {
                    "access_token": "new_access_token",
                    "expires_in": 3600,
                    
                }

        # Replace the real HTTP request with our fake response
        def fake_post(*args, **kwargs):
            return FakeResponse()

        monkeypatch.setattr(requests, "post", fake_post)

        # Act: run the actual refresh function
        result = app.refresh_access_token()

        # Assert: verify the refresh worked
        assert result is True
        assert session["access_token"] == "new_access_token"
        assert session["expires_at"] > time.time()
        assert session["refresh_token"] == "old_refresh_token"


def test_refresh_access_token_invalid_grant(monkeypatch):
    with app.app.test_request_context("/"):
        # Arrange: simulate an existing session with tokens
        session["access_token"] = "old_access_token"
        session["refresh_token"] = "invalid_refresh_token"
        session["expires_at"] = 9999999999

        # Simulate Spotify rejecting the refresh token
        class FakeResponse:
            status_code = 400

            def json(self):
                return {"error": "invalid_grant"}

        def fake_post(*args, **kwargs):
            return FakeResponse()

        monkeypatch.setattr(requests, "post", fake_post)

        # Act: call the actual refresh function
        result = app.refresh_access_token()

        # Assert: refresh fails
        assert result is False

        # Assert: all three token-related session keys are cleared
        assert "access_token" not in session
        assert "refresh_token" not in session
        assert "expires_at" not in session


def test_refresh_access_token_http_error(monkeypatch):
    with app.app.test_request_context("/"):
        # Arrange: provide a refresh token
        session["refresh_token"] = "existing_refresh_token"

        # Simulate Spotify returning HTTP 500
        class FakeResponse:
            status_code = 500

            def raise_for_status(self):
                raise requests.HTTPError("Spotify server error")

        def fake_post(*args, **kwargs):
            return FakeResponse()

        monkeypatch.setattr(requests, "post", fake_post)

        # Act
        result = app.refresh_access_token()

        # Assert
        assert result is False
        assert session["refresh_token"] == "existing_refresh_token"


#to handle spotify api request in case of connection failure

def test_spotify_api_request_network_error(monkeypatch):
    with app.app.test_request_context("/"):
        # Arrange: provide a valid access token
        session["access_token"] = "valid_access_token"
        session["expires_at"] = time.time() + 3600

        # Simulate a network failure
        def fake_get(*args, **kwargs):
            raise requests.ConnectionError("Network unavailable")

        monkeypatch.setattr(requests, "get", fake_get)

        # Act
        result, error = app.spotify_api_request("me")

        # Assert
        assert result is None
        assert error == "request_failed"

def test_top_routes_handle_rate_limit():
    mock_response = Mock()
    mock_response.ok = False
    mock_response.status_code = 429

    routes = ["/top/artists", "/top/tracks"]

    for route in routes:
        with patch("app.spotify_api_request", return_value=(mock_response, None)):
            response = app.app.test_client().get(route)

        assert response.status_code == 429
        

def test_top_routes_handle_missing_items():
    mock_response = Mock()
    mock_response.ok = True
    mock_response.json.return_value = {}

    routes = ["/top/artists", "/top/tracks"]

    for route in routes:
        with patch("app.spotify_api_request", return_value=(mock_response, None)):
            response = app.app.test_client().get(route)

        assert response.status_code == 500



