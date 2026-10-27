# mocking-> not depending on actual sebers for the response data
# this makes testing fast
# hence we add mock spotify_api_request() and return a fake response
# this test does not prove that Spotify login or token refresh works. It isolates the route's behavior: given a successful helper response, does the route return the correct JSON?

from unittest.mock import patch, Mock

from app import app


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
        client = app.test_client() # lets us send requests to Flask without starting a server or opening a browser.
        response = client.get("/top/artists")

    # Check the result
    assert response.status_code == 200

    result = response.get_json()
    assert result["top_artists"][0]["name"] == "Test Artist"
    assert result["top_artists"][0]["id"] == "artist123"
    assert result["top_artists"][0]["spotify_url"] == (
        "https://open.spotify.com/artist/artist123"
    )



