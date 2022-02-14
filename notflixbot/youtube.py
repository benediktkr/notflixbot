from urllib.parse import parse_qs, urljoin, urlparse

import requests
from loguru import logger
from requests.exceptions import ReadTimeout, RequestException


class Youtube:
    def __init__(self, config):
        self.iv_url = config['invidious_url']

    def get_youtube_video_id(self, youtube_url):
        if "youtube.com" in youtube_url:
            q = parse_qs(urlparse(youtube_url).query)
            if 'v' in q:
                # parse_qs returns a list if 'v' in q,
                # but raises a KeyERror if it isnt in q
                # so this is safe
                return q['v'][0]

        elif "youtu.be" in youtube_url:
            p = urlparse(youtube_url).path[1:]
            return p

        else:
            raise ValueError("no youtube id found")

    async def unfurl(self, msg_body):
        for w in msg_body.split(' '):
            try:
                ytid = self.get_youtube_video_id(w.strip())
                iv_videos = urljoin(self.iv_url, "/api/v1/videos/")
                iv_api_url = urljoin(iv_videos, ytid)

                r = requests.get(iv_api_url, timeout=4.20)
                r.raise_for_status()
                j = r.json()

                title = j['title']
                iv_url = urljoin(self.iv_url, "/watch?v=") + ytid

                msg = f"🎥 {title} | [YouBahn]({iv_url})"
                plain = f"🎥 {title}"
                return (msg, plain)

            except (ValueError, ReadTimeout, RequestException) as e:
                logger.warning(e)
                return None
