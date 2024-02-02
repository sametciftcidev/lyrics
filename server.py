import os
from flask import Flask
import lyricsgenius
import requests

genius = lyricsgenius.Genius("toJOqCi-0052N13HZFuoK-utQWN-404ffSTVNsPXk0EPfDlKTdyvv60XL1eDxb3K")

app = Flask(__name__)

port = int(os.environ.get("PORT", 5000))


@app.route("/api")
def hi_world():
    shoutcastRequest = requests.get('http://s10.voscast.com:10348/currentsong?sid=1')

    # songTitle = shoutcastRequest.text
    songTitle = "Kalbim Ağlama Kurtuluş Kuş & Siyam"

    lyrics = ""

    itunesResponse = requests.get('https://itunes.apple.com/search?term=' + songTitle)

    if itunesResponse.status_code == 200:
        itunesResponse = itunesResponse.json()

        if itunesResponse['resultCount'] > 0:

            result = itunesResponse['results'][0]

            trackName = result['trackName']
            artistName = result['artistName']

            song = genius.search_song(title=trackName, artist=artistName, get_full_info=False)

            if song is not None:
                if result['artistName'] == song.artist:
                    lyrics = song.lyrics

    return {
        "songTitle": songTitle,
        "lyrics": lyrics
    }


if __name__ == "__main__":
    app.run(port=port)
