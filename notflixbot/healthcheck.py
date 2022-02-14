import sys

import requests
from loguru import logger


def healthcheck(host, port):
    if host == "0.0.0.0":
        host = "127.0.0.1"

    try:
        url = f"http://{host}:{port}/ruok"
        r = requests.get(url, timeout=0.1)
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        logger.error(e)
        sys.exit(1)

    if j['ruok'] == "iamok" and r.status_code == 200:
        sys.exit(0)
    else:
        sys.exit(1)
