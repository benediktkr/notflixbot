import argparse

from loguru import logger

from notflixbot.errors import ConfigError
from notflixbot.config import Config
from notflixbot.notflixbot import NotflixMatrixClient
from notflixbot import __version__


def get_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-c", "--config",
                        help="path to config file", default="config.json")
    parser.add_argument("-r", "--restore-login", action="store_true",
                        help="overwrite credentials if they exit")
    parser.add_argument("--debug", action="store_true",
                        help="print debug output")

    return parser


def get_args():
    return get_parser().parse_args()


@logger.catch
def main():
    try:
        args = get_args()

        config = Config.read(args.config, args.debug)

        logger.info(f"{__name__} {__version__} - {config.user_id}")

    except ConfigError as e:
        logger.error(e)
        raise SystemExit(2) from e

    NotflixMatrixClient.run_async(config, args)
