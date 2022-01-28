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
            'QualityProfileId': 4,   # HD 1080
            # 'Path': self.path,
            'RootFolderPath': "/deadspace/video/movies",
            'monitored': True,
            'addOptions': {'searchForMovie': True}

        }, indent=2)
        r = requests.post(
            f"{self._base_url}/movie",
            data=data,
            params={'apikey': self._api_key},
            headers={'Content-Type': 'application/json'}
        )
        j = r.json()
        logger.info(f"radarr responded: {r.status_code}")
        return (r.status_code, j)


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
            status, response = self.radarr.add(item)
            added = status == 201
            return (added, item)

            # msg = f"{item['title']} ({item['release_year']})"
            # msg += " | [poster]({item['poster']})"
            # return {
            #     'msg': msg,
            #     'item': item
            # }
        except (ImdbError, TvdbError, NotImplementedError) as e:
            raise NotflixbotError(e) from e
