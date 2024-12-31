import argparse
import asyncio
from asyncio import TimeoutError
from asyncio.exceptions import CancelledError
from time import sleep

import zmq.asyncio
from aiohttp import ClientConnectionError, ServerDisconnectedError
from loguru import logger

from notflixbot import version_dict
from notflixbot.config import Config
from notflixbot.errors import ConfigError
from notflixbot.healthcheck import healthcheck
from notflixbot.matrix import MatrixClient
from notflixbot.webhook import Webhook


def get_parser():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    subparser = parser.add_subparsers(dest='subcmd', metavar='subcmd')
    subparser.required = True

    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output and logging")
    parser.add_argument("-c", "--config", help="Path to config file", default="/etc/notflixbot.json")

    subparser.add_parser("start", help="Start Matrix bot and webhook HTTP server")
    subparser.add_parser("restore_login", help="Start a new Matrix session")
    subparser.add_parser("webhook", help="Start webhook HTTP server")
    healthcheck_parser = subparser.add_parser("Healthcheck", help="Run healthcheck for webhook HTTP server")
    healthcheck_parser.add_argument("--quiet", action="store_true")
    nio_parser = subparser.add_parser("nio", help="Low-level stuff, helpful for dev")
    nio_parser.add_argument("--forget-room", type=str, required=True, help="The canonical_alias or room_id of a room to forget")

    return parser


@logger.catch
@MatrixClient.catch
async def async_main(args, config):
    logger.success(f"{version_dict['name']} {version_dict['version']}")

    ctx = zmq.asyncio.Context()
    try:
        webhook = Webhook(config, ctx)

        if args.subcmd == "webhook":
            await webhook.serve()
            await asyncio.sleep(3600)

        async with MatrixClient(config, ctx) as matrix:
            if args.subcmd == "start":

                await matrix.auth()

                await asyncio.gather(
                    asyncio.create_task(matrix._after_first_sync()),
                    asyncio.create_task(matrix.sync_forever()),
                    asyncio.create_task(matrix.webhook_poller()),
                    asyncio.create_task(webhook.serve())
                )

            if args.subcmd == "restore_login":
                await matrix.restore_login()

            if args.subcmd == "nio":
                if args.forget_room:
                    await matrix._set_creds()
                    await matrix._key_sync()

                    room_id = await matrix._room_id(args.forget_room)
                    await matrix.nio.room_leave(room_id)
                    await matrix.nio.room_forget(room_id)
                    logger.info(f"Forgot room {args.forget_room}")

    except CancelledError:
        logger.info("Cancelled")
        ctx.destroy()

    except (ClientConnectionError, ServerDisconnectedError, TimeoutError):
        logger.warning("Unable to connect to homeserver, retrying in 15s...")
        sleep(15)


def main():
    try:
        parser = get_parser()
        args = parser.parse_args()
        config = Config.read(args.config, args.debug)
    except ConfigError as e:
        logger.error(e)
        raise SystemExit(2) from e

    if args.subcmd == "healthcheck":
        return healthcheck(config.webhook_host, config.webhook_port, args.quiet)

    while True:
        try:
            asyncio.run(
                async_main(args, config)
            )
        except KeyboardInterrupt:
            logger.warning("C-c was passed, exiting..")
            raise SystemExit(1)
        except Exception as e:
            # staying alive!
            logger.exception(e)
            logger.warning("Reconnecting..")
            sleep(4.20)
