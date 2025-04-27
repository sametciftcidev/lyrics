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
import redis

genius = lyricsgenius.Genius("mgIU1E6HvQeTBAZotm__aBP0qYDD6TvOIm-5xwuVA-scbhNa9kShRdC7c92yBdoK")

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})

port = int(os.environ.get("PORT", 5000))

notSong = ["Mega Radio London", "Slov", "Duyuru", "Jingle", "Remix", "SIIR", "MEGA RADIO LONDON"]

# Redis configuration
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')

try:
    redis_client = redis.from_url(redis_url)
    # Test the connection
    redis_client.ping()
    print("Successfully connected to Redis")
except Exception as e:
    print(f"Redis connection error: {str(e)}")
    redis_client = None

def get_cache(key):
    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"Redis get error: {str(e)}")
        return None

def set_cache(key, value):
    try:
        redis_client.set(key, json.dumps(value))
        print(f"Cached data for {key}")
    except Exception as e:
        print(f"Redis set error: {str(e)}")

def get_lyrics_from_musixmatch(title, artist, original_title):
    try:
        response = requests.get(f'https://lyrics-api-steel.vercel.app/musixmatch/lyrics-search?title={quote(title)}&artist={quote(artist)}')
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('lyrics', '')
            if lyrics:
                # Cache the successful result using original title
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
        genius.verbose = False
        genius.remove_section_headers = True
        genius.skip_non_songs = False
        genius.excluded_terms = ["(Remix)", "(Live)"]
        
        song = genius.search_song(title=title, artist=artist, get_full_info=True)
        if song is not None and artist == song.artist:
            lyrics = unidecode.unidecode(song.lyrics)
            if lyrics:
                # Cache the successful result using original title
                cache_data = {
                    'source': 'Genius',
                    'lyrics': lyrics
                }
                set_cache(original_title, cache_data)
                print(f"Cached Genius result for {original_title}")
            return lyrics, 'Genius'
    except Exception as e:
        print(f"Genius error: {str(e)}")
    return '', ''

def get_lyrics_from_youtube(title, original_title):
    try:
        response = requests.get(f'https://lyrics-api-steel.vercel.app/youtube/lyrics?title={quote(title)}')
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('lyrics', '')
            if lyrics:
                # Decode Unicode escape sequences
                lyrics = lyrics.encode('utf-8').decode('unicode-escape')
                # Cache the successful result using original title
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
        shoutcastRequest = requests.get('http://s10.voscast.com:10348/currentsong?sid=1')
        shoutcastRequest.raise_for_status()
        
        songTitle = unidecode.unidecode(shoutcastRequest.text)
        lyrics = ""
        lyricsSource = ""
        artworkUrl = ""
        
        isNotSong = any(ext in songTitle for ext in notSong)
        
        if not isNotSong:
            encoded_song = quote(songTitle)
            itunesResponse = requests.get(f'https://itunes.apple.com/search?term={encoded_song}')
            itunesResponse.raise_for_status()
            
            itunesData = itunesResponse.json()
            
            if itunesData['resultCount'] > 0:
                result = itunesData['results'][0]
                trackName = result['trackName']
                artistName = result['artistName']
                artworkUrl = result['artworkUrl100'].replace('100', '600')
                
                # Check cache first using the exact songTitle
                print(f"Checking cache for key: {songTitle}")
                cached_data = get_cache(songTitle)
                
                if cached_data:
                    print(f"Found cached result: {cached_data['source']}")
                    lyrics = cached_data['lyrics']
                    lyricsSource = cached_data['source']
                else:
                    print("No cached result found, trying services in sequence")
                    # Try YouTube Music first, then fall back to others
                    lyrics, lyricsSource = get_lyrics_from_youtube(trackName, songTitle)
                    if not lyrics:
                        lyrics, lyricsSource = get_lyrics_from_musixmatch(trackName, artistName, songTitle)
                    if not lyrics:
                        lyrics, lyricsSource = get_lyrics_from_genius(trackName, artistName, songTitle)
        
        value = {
            "songTitle": songTitle,
            "lyrics": lyrics,
            "lyricsSource": lyricsSource,
            "artworkUrl": artworkUrl
        }
        
        return jsonify(value)
        
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({
            "error": "An error occurred while processing your request",
            "songTitle": "",
            "lyrics": "",
            "lyricsSource": "",
            "artworkUrl": ""
        }), 500

if __name__ == "__main__":
    app.run(port=port)