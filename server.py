import os

from flask import Flask, json, jsonify
import lyricsgenius
import requests
import unidecode
from flask_cors import CORS

genius = lyricsgenius.Genius("mgIU1E6HvQeTBAZotm__aBP0qYDD6TvOIm-5xwuVA-scbhNa9kShRdC7c92yBdoK")

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})

port = int(os.environ.get("PORT", 5000))

notSong = ["Mega Radio London", "Slov", "Duyuru", "Jingle", "Remix", "SIIR", "MEGA RADIO LONDON"]

@app.route("/api")
def hi_world():
    shoutcastRequest = requests.get('http://s10.voscast.com:10348/currentsong?sid=1')

    songTitle = unidecode.unidecode(shoutcastRequest.text)
    # songTitle = unidecode.unidecode("12-Slov")
    # songTitle = unidecode.unidecode("Kalbim Ağlama Kurtuluş Kuş & Siyam")

    lyrics = ""
    artworkUrl = ""

    isNotSong = any(ext in songTitle for ext in notSong)

    itunesResponse = requests.get('https://itunes.apple.com/search?term=' + songTitle)

    if itunesResponse.status_code == 200:
        itunesResponse = itunesResponse.json()

        if itunesResponse['resultCount'] > 0:

            result = itunesResponse['results'][0]

            trackName = result['trackName']
            artistName = result['artistName']

            if isNotSong:
                artworkUrl = ""
            else:
                artworkUrl = result['artworkUrl100']
                artworkUrl = artworkUrl.replace('100', '600')

            genius.verbose = False  # Turn off status messages
            genius.remove_section_headers = True  # Remove section headers (e.g. [Chorus]) from lyrics when searching
            genius.skip_non_songs = False  # Include hits thought to be non-songs (e.g. track lists)
            genius.excluded_terms = ["(Remix)", "(Live)"]  # Exclude songs with these words in their title

            song = genius.search_song(title=trackName, artist=artistName, get_full_info=True)

            if song is not None:
                if result['artistName'] == song.artist:
                    lyrics = unidecode.unidecode(song.lyrics)
                    # fetchedLyrics = song.lyrics.replace("\n", "<br/>")
                    # lyrics = unidecode.unidecode(fetchedLyrics)

    value = {
        "songTitle": songTitle,
        "lyrics": lyrics,
        "artworkUrl": artworkUrl
    }

    response = app.response_class(
        response=json.dumps(value),
        status=200,
        mimetype='application/json'
    )

    return response


if __name__ == "__main__":
    app.run(port=port)
