import os
from flask import Flask, json, jsonify
import lyricsgenius
import requests
import unidecode

genius = lyricsgenius.Genius("toJOqCi-0052N13HZFuoK-utQWN-404ffSTVNsPXk0EPfDlKTdyvv60XL1eDxb3K")

app = Flask(__name__)

port = int(os.environ.get("PORT", 5000))


@app.route("/api")
def hi_world():
    shoutcastRequest = requests.get('http://s10.voscast.com:10348/currentsong?sid=1')

    # songTitle = unidecode.unidecode(shoutcastRequest.text)
    songTitle = unidecode.unidecode("Kalbim Ağlama Kurtuluş Kuş & Siyam")

    lyrics = ""

    itunesResponse = requests.get('https://itunes.apple.com/search?term=' + songTitle)

    if itunesResponse.status_code == 200:
        itunesResponse = itunesResponse.json()

        if itunesResponse['resultCount'] > 0:

            result = itunesResponse['results'][0]

            trackName = result['trackName']
            artistName = result['artistName']

            genius.verbose = False  # Turn off status messages
            genius.remove_section_headers = True  # Remove section headers (e.g. [Chorus]) from lyrics when searching
            genius.skip_non_songs = False  # Include hits thought to be non-songs (e.g. track lists)
            genius.excluded_terms = ["(Remix)", "(Live)"]  # Exclude songs with these words in their title

            song = genius.search_song(title=trackName, artist=artistName, get_full_info=True)

            if song is not None:
                if result['artistName'] == song.artist:
                    lyrics = unidecode.unidecode(song.lyrics)

    value = {
        "songTitle": songTitle,
        "lyrics": lyrics
    }

    response = app.response_class(
        response=json.dumps(value),
        status=200,
        mimetype='application/json'
    )

    return response


if __name__ == "__main__":
    app.run(port=port)
