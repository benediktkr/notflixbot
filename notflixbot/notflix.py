import json

from urllib.parse import urlparse
from urllib.parse import urljoin

import requests
from loguru import logger

from notflixbot.errors import ImdbError, TvdbError, NotflixbotError

class Radarr:
    def __init__(self, base_url, api_key):
        self._api_key = api_key
        self._base_url = base_url

    def add(self, item):
        data = json.dumps({
            'imdbId': item['imdb_id'],
            'TmdbId': item['tmdb_id'],
            'Title': item['title'],
            'QualityProfileId': 4, # HD 1080
            # 'Path': self.path,
            'RootFolderPath': f"/deadspace/video/movies",
            'monitored': True,
            'addOptions': {'searchForMovie': True}

        }, indent=2)
        print(data)
        """
        {
  "title": "Zola",
  "originalTitle": "Zola",
  "alternateTitles": [],
  "secondaryYear": 2020,
  "secondaryYearSourceId": 0,
  "sortTitle": "zola",
  "sizeOnDisk": 0,
  "status": "released",
  "overview": "A waitress agrees to accompany an exotic dancer, her put-upon boyfriend, and her mysterious and domineering roommate on a road trip to Florida to seek their fortune at a high-end strip club.",
  "inCinemas": "2021-06-30T00:00:00Z",
  "physicalRelease": "2021-09-14T00:00:00Z",
  "digitalRelease": "2021-07-21T00:00:00Z",
  "images": [
    {
      "coverType": "poster",
      "url": "/radarr/MediaCover/147/poster.jpg",
      "remoteUrl": "https://image.tmdb.org/t/p/original/bJLCPROp9bmNndurwZpVnOioVpB.jpg"
    },
    {
      "coverType": "fanart",
      "url": "/radarr/MediaCover/147/fanart.jpg",
      "remoteUrl": "https://image.tmdb.org/t/p/original/pc471CQr2IzdnfiJTspjtW4ktRC.jpg"
    }
  ],
  "website": "https://a24films.com/films/zola",
  "year": 2021,
  "hasFile": false,
  "youTubeTrailerId": "jrQFYJPkp_U",
  "studio": "Killer Films",
  "path": "/deadspace/video/movies/Zola (2021)",
  "qualityProfileId": 4,
  "monitored": true,
  "minimumAvailability": "tba",
  "isAvailable": true,
  "folderName": "/deadspace/video/movies/Zola (2021)",
  "runtime": 86,
  "cleanTitle": "zola",
  "imdbId": "tt5439812",
  "tmdbId": 539565,
  "titleSlug": "539565",
  "certification": "R",
  "genres": [
    "Comedy",
    "Crime"
  ],
  "tags": [],
  "added": "2022-01-11T09:02:51Z",
  "addOptions": {
    "searchForMovie": true,
    "ignoreEpisodesWithFiles": false,
    "ignoreEpisodesWithoutFiles": false
  },
  "ratings": {
    "votes": 76,
    "value": 6.3
  },
  "id": 147
}
        """

        r = requests.post(
            f"{self._base_url}/movie",
            data=data,
            params={'apikey': self._api_key},
            headers={'Content-Type': 'application/json'}
        )
        j = r.json()
        print(json.dumps(j, indent=2))



class TheMovieDB:
    def __init__(self, api_key):
        self._api_key = api_key

        self.poster_base_url = "https://www.themoviedb.org/t/p/w1280"
        self.api_base_url = "https://api.themoviedb.org/3/"

    # https://developers.themoviedb.org/3/find/find-by-id
    def search_imdb_id(self, imdb_id):
        url = urljoin(self.api_base_url, f"find/{imdb_id}")
        params = {
            'api_key': self._api_key,
            # 'language': 'en-US',
            'external_source': 'imdb_id'
        }
        r = requests.get(url, params=params)
        r.raise_for_status()
        j = r.json()

        print(json.dumps(j, indent=2))

        info = self.parse_tvdb(j, imdb_id)
        if info is None:
            err = f"no results in tv or movies for '{imdb_id}'"
            logger.error(err)
            raise TvdbError(err)
        return info

    def parse_tvdb(self, j, imdb_id):
        if j['movie_results']:
            if len(j['movie_results']) > 1:
                logger.warn("multiple results, using the first (for now)")

            m = j['movie_results'][0]
            return {
                't': "movie",
                'poster': f"{self.poster_base_url}{m['poster_path']}",
                'backdrop': f"{self.poster_base_url}{m['backdrop_path']}",
                'release_date': m['release_date'],
                'release_year': m['release_date'].split('-')[0],
                'title': m['title'],
                'original_title': m.get('original_title', ""),
                'tmdb_id': int(m['id']),
                'vote_average': m['vote_average'],
                'imdb_id': imdb_id
            }

        elif j['tv_results']:
            logger.warning("tv show requested")
            raise NotImplementedError("currently this only works for movies")
        else:
            return None


class Notflix:

    def __init__(self, config_dict):
        self.config_dict = config_dict
        self.tvdb = TheMovieDB(config_dict['themoviedb_api_key'])
        self.radarr = Radarr(config_dict['radarr_url'],
                             config_dict['radarr_api_key'])

    def get_imdb_id_from_url(self, url):
        parsed_url = urlparse(url)
        if parsed_url.netloc.endswith("imdb.com"):
            path_parts = parsed_url.path.split('/')
            if path_parts[1] != "title":
                logger.warning(f"weird url? {url}")
            imdb_id = path_parts[2]
            return imdb_id
        else:
            raise ImdbError("not an imdb url")

    def add_from_imdb_url(self, imdb_url):
        try:
            imdb_id = self.get_imdb_id_from_url(imdb_url)
            item = self.tvdb.search_imdb_id(imdb_id)
            self.radarr.add(item)
            return item

            # msg = f"{item['title']} ({item['release_year']})"
            # msg += " | [poster]({item['poster']})"
            # return {
            #     'msg': msg,
            #     'item': item
            # }
        except (ImdbError, TvdbError, NotImplementedError) as e:
            raise NotflixbotError(e) from e
