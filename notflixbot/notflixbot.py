from urllib.parse import urlparse
from urllib.parse import urljoin

import requests
from loguru import logger

from notflixbot.errors import ImdbError, TvdbError, NotflixbotError

API_BASE_URL = "https://api.themoviedb.org/3/"
POSTER_BASE_URL = "https://www.themoviedb.org/t/p/w1280"


class TheMovieDB:
    def __init__(self, api_key):
        self._api_key = api_key

    # https://developers.themoviedb.org/3/find/find-by-id
    def search_imdb_id(self, imdb_id):
        url = urljoin(API_BASE_URL, f"find/{imdb_id}")
        params = {
            'api_key': self._api_key,
            # 'language': 'en-US',
            'external_source': 'imdb_id'
        }
        r = requests.get(url, params=params)
        r.raise_for_status()
        j = r.json()

        info = self.parse_tvdb(j)
        if info is None:
            err = f"no results in tv or movies for '{imdb_id}'"
            logger.error(err)
            raise TvdbError(err)
        return info

    def parse_tvdb(self, j):
        if j['movie_results']:
            if len(j['movie_results']) > 1:
                logger.warn("multiple results, using the first (for now)")

            m = j['movie_results'][0]
            return {
                't': "movie",
                'poster': f"{POSTER_BASE_URL}{m['poster_path']}",
                'backdrop': f"{POSTER_BASE_URL}{m['backdrop_path']}",
                'release_date': m['release_date'],
                'release_year': m['release_date'].split('-')[0],
                'title': m['title'],
                'original_title': m.get('original_title', ""),
                'tmdb_id': str(m['id']),
                'vote_average': m['vote_average']
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
            info = self.tvdb.search_imdb_id(imdb_id)

            msg = f"{info['title']} ({info['release_year']})"
            msg += " | [poster]({info['poster']})"
            return {
                'msg': msg,
                'info': info
            }
        except (ImdbError, TvdbError, NotImplementedError) as e:
            raise NotflixbotError(e) from e
