import os
import json
from flask import Flask, json, jsonify
import lyricsgenius
import requests
import unidecode
from flask_cors import CORS
from urllib.parse import quote
from functools import lru_cache
import re
from upstash_redis import Redis
import time
from datetime import datetime

# WebShare API configuration
WEBSHARE_API_TOKEN = "200w30fysh098lufdfj8pe7gza39cvb81pv0j8wi"
WEBSHARE_API_URL = "https://proxy.webshare.io/api/v2/proxy/list/"

# Fallback configuration
FALLBACK_SONG_TITLE = "Mega Radio London"
FALLBACK_LYRICS = ""
FALLBACK_ARTWORK = "https://s3.gifyu.com/images/bb6mp.gif"

def get_webshare_proxies():
    try:
        response = requests.get(
            WEBSHARE_API_URL,
            headers={"Authorization": f"Token {WEBSHARE_API_TOKEN}"},
            params={
                "mode": "direct",
                "page": 1,
                "page_size": 25
            },
            timeout=5  # Add timeout
        )
        response.raise_for_status()
        data = response.json()
        
        proxies = []
        for proxy in data.get('results', []):
            if proxy.get('valid'):
                proxy_url = f"http://{proxy['username']}:{proxy['password']}@{proxy['proxy_address']}:{proxy['port']}"
                proxies.append({
                    'url': proxy_url,
                    'country': proxy.get('country_code'),
                    'city': proxy.get('city_name'),
                    'last_verified': proxy.get('last_verification')
                })
        return proxies
    except Exception as e:
        print(f"Error fetching WebShare proxies: {str(e)}")
        return []

def get_current_proxy():
    try:
        proxies = get_webshare_proxies()
        if proxies:
            import random
            proxy = random.choice(proxies)
            print(f"Using proxy from {proxy['country']} ({proxy['city']})")
            return proxy['url']
    except Exception as e:
        print(f"Error getting current proxy: {str(e)}")
    return None

def init_genius_client():
    try:
        proxy_url = get_current_proxy()
        if proxy_url:
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            print(f"Initializing Genius client with proxy: {proxy_url}")
        else:
            proxies = None
            print("No proxy available, using direct connection")
        
        return lyricsgenius.Genius(
            "mgIU1E6HvQeTBAZotm__aBP0qYDD6TvOIm-5xwuVA-scbhNa9kShRdC7c92yBdoK",
            proxy=proxies,
            timeout=15,
            retries=3,
            verbose=True
        )
    except Exception as e:
        print(f"Error initializing Genius client: {str(e)}")
        return None

# Initialize Genius client
genius = init_genius_client()

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})

port = int(os.environ.get("PORT", 5000))

notSong = ["Mega Radio London", "Slov", "Duyuru", "Jingle", "Remix", "SIIR", "MEGA RADIO LONDON"]

# Redis configuration
REDIS_URL = "https://dynamic-pigeon-18181.upstash.io"
REDIS_TOKEN = "AUcFAAIjcDFlYzI2NmU4YTU4NGI0MmZiOWFkMjRkZjMwM2Y3ZDViN3AxMA"
redis_client = None

def init_redis_client():
    global redis_client
    try:
        print("Attempting to connect to Upstash Redis...")
        redis_client = Redis(url=REDIS_URL, token=REDIS_TOKEN)
        
        # Test the connection
        print("Testing Redis connection...")
        test_key = "test_connection"
        redis_client.set(test_key, "test_value")
        test_value = redis_client.get(test_key)
        
        if test_value == "test_value":
            print("Successfully connected to Redis and verified write/read")
            redis_client.delete(test_key)
            return True
        else:
            print("Redis connection test failed - write/read verification failed")
            redis_client = None
            return False
            
    except Exception as e:
        print(f"Redis connection error: {str(e)}")
        redis_client = None
        return False

# Initialize Redis client
if not init_redis_client():
    print("Failed to initialize Redis client. Will retry on first cache operation.")

def get_cache(key):
    global redis_client
    if redis_client is None:
        print("Redis client not available, attempting to reconnect...")
        if not init_redis_client():
            print("Failed to reconnect to Redis")
            return None
    
    try:
        data = redis_client.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError as e:
                print(f"Error decoding cached data: {str(e)}")
                return None
        return None
    except Exception as e:
        print(f"Redis get error for key {key}: {str(e)}")
        return None

def set_cache(key, value):
    global redis_client
    if redis_client is None:
        print("Redis client not available, attempting to reconnect...")
        if not init_redis_client():
            print("Failed to reconnect to Redis")
            return
    
    try:
        # Convert value to JSON string
        json_value = json.dumps(value)
        # Set with expiration (24 hours)
        redis_client.setex(key, 86400, json_value)
        print(f"Successfully cached data for {key}")
        
        # Verify the data was saved
        cached_data = redis_client.get(key)
        if cached_data:
            print(f"Verified cache write for {key}")
        else:
            print(f"Cache verification failed for {key}")
    except Exception as e:
        print(f"Redis set error for key {key}: {str(e)}")

def get_lyrics_from_musixmatch(title, artist, original_title):
    try:
        response = requests.get(
            f'https://lyrics-api-steel.vercel.app/musixmatch/lyrics-search?title={quote(title)}&artist={quote(artist)}',
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('lyrics', '')
            if lyrics:
                lyrics = unidecode.unidecode(lyrics)
                cache_data = {
                    'source': 'Musixmatch',
                    'lyrics': lyrics
                }
                set_cache(original_title, cache_data)
                print(f"Cached Musixmatch result for {original_title}")
                return lyrics, 'Musixmatch'
    except Exception as e:
        print(f"Musixmatch error: {str(e)}")
    return '', ''

def get_lyrics_from_genius(title, artist, original_title):
    try:
        global genius
        if not genius:
            genius = init_genius_client()
            if not genius:
                return '', ''

        if time.time() - getattr(genius, '_last_proxy_refresh', 0) > 3600:
            genius = init_genius_client()
            genius._last_proxy_refresh = time.time()
        
        genius.verbose = True
        genius.remove_section_headers = True
        genius.skip_non_songs = False
        genius.excluded_terms = ["(Remix)", "(Live)"]
        
        # Clean up the title and artist for better search
        clean_title = title.split('(')[0].strip()  # Remove anything in parentheses
        clean_artist = artist.split('&')[0].strip() if artist else ""  # Take first artist if multiple
        
        # Try the original search approach
        try:
            print(f"Trying Genius search with: {clean_title} - {clean_artist}")
            song = genius.search_song(title=clean_title, artist=clean_artist, get_full_info=True)
            if song is not None:
                print(f"Found song: {song.title} by {song.artist}")
                lyrics = unidecode.unidecode(song.lyrics)
                if lyrics:
                    # Create cache data
                    cache_data = {
                        'source': 'Genius',
                        'lyrics': lyrics,
                        'timestamp': datetime.now().isoformat()
                    }
                    # Save to Redis with verification
                    set_cache(original_title, cache_data)
                    return lyrics, 'Genius'
        except Exception as e:
            print(f"Genius search error: {str(e)}")
        
        print("No matching song found in Genius")
        return '', ''
        
    except Exception as e:
        print(f"Genius error: {str(e)}")
        try:
            genius = init_genius_client()
            return get_lyrics_from_genius(title, artist, original_title)
        except:
            pass
    return '', ''

def get_lyrics_from_youtube(title, original_title):
    try:
        response = requests.get(
            f'https://lyrics-api-steel.vercel.app/youtube/lyrics?title={quote(title)}',
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('lyrics', '')
            if lyrics:
                lyrics = unidecode.unidecode(lyrics)
                cache_data = {
                    'source': 'YouTube Music',
                    'lyrics': lyrics
                }
                set_cache(original_title, cache_data)
                print(f"Cached YouTube result for {original_title}")
                return lyrics, 'YouTube Music'
    except Exception as e:
        print(f"YouTube error: {str(e)}")
    return '', ''

@app.route("/api")
def hi_world():
    try:
        # Try to get current song
        try:
            shoutcastRequest = requests.get('http://s10.voscast.com:10348/currentsong?sid=1', timeout=5)
            shoutcastRequest.raise_for_status()
            songTitle = unidecode.unidecode(shoutcastRequest.text)
        except Exception as e:
            print(f"Shoutcast error: {str(e)}")
            songTitle = FALLBACK_SONG_TITLE

        lyrics = ""
        lyricsSource = ""
        artworkUrl = FALLBACK_ARTWORK
        
        isNotSong = any(ext in songTitle for ext in notSong)
        
        if not isNotSong:
            try:
                encoded_song = quote(songTitle)
                itunesResponse = requests.get(f'https://itunes.apple.com/search?term={encoded_song}', timeout=5)
                itunesResponse.raise_for_status()
                
                itunesData = itunesResponse.json()
                
                if itunesData['resultCount'] > 0:
                    result = itunesData['results'][0]
                    trackName = result['trackName']
                    artistName = result['artistName']
                    artworkUrl = result['artworkUrl100'].replace('100', '600')
                    
                    # Check cache first
                    print(f"Checking cache for key: {songTitle}")
                    cached_data = get_cache(songTitle)
                    
                    if cached_data:
                        print(f"Found cached result: {cached_data['source']}")
                        lyrics = cached_data['lyrics']
                        lyricsSource = cached_data['source']
                    else:
                        print("No cached result found, trying services in sequence")
                        # Try all services
                        lyrics, lyricsSource = get_lyrics_from_youtube(trackName, songTitle)
                        if not lyrics:
                            lyrics, lyricsSource = get_lyrics_from_musixmatch(trackName, artistName, songTitle)
                        if not lyrics:
                            lyrics, lyricsSource = get_lyrics_from_genius(trackName, artistName, songTitle)
            except Exception as e:
                print(f"iTunes/lyrics error: {str(e)}")
        
        # Ensure we always have some response
        if not lyrics:
            lyrics = FALLBACK_LYRICS
            lyricsSource = "No source available"
        
        value = {
            "songTitle": songTitle,
            "lyrics": lyrics,
            "lyricsSource": lyricsSource,
            "artworkUrl": artworkUrl
        }
        
        return jsonify(value)
        
    except Exception as e:
        print(f"API Error: {str(e)}")
        # Return fallback response
        return jsonify({
            "songTitle": FALLBACK_SONG_TITLE,
            "lyrics": FALLBACK_LYRICS,
            "lyricsSource": "Error occurred",
            "artworkUrl": FALLBACK_ARTWORK
        }), 200  # Return 200 instead of 500 to ensure client always gets a response

if __name__ == "__main__":
    app.run(port=port)