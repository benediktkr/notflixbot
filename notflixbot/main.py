import argparse
import asyncio
from time import sleep

from loguru import logger
import zmq.asyncio
from aiohttp import ClientConnectionError, ServerDisconnectedError

from notflixbot.errors import ConfigError
from notflixbot.config import Config
from notflixbot.matrix import MatrixClient
from notflixbot.webhook import Webhook


def get_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    subparser = parser.add_subparsers(dest='subcmd', metavar='subcmd')
    subparser.required = True

    parser.add_argument("-d", "--debug", action="store_true",
                        help="print debug output")
    parser.add_argument("-c", "--config",
                        help="path to config file",
                        default="/etc/notflixbot.json")

    subparser.add_parser("start", help="start matrix bot")
    subparser.add_parser("restore_login", help="start new matrix session")
    subparser.add_parser("webhook", help="start webhook http server")
    nio_parser = subparser.add_parser("nio",
                                      help="low-level stuff, helpful for dev")
    nio_parser.add_argument("--forget-room", type=str, required=True,
                            help="canonical_alias or room_id")

    return parser


@logger.catch
@MatrixClient.catch
async def async_main():
    try:
        parser = get_parser()
        args = parser.parse_args()

        config = Config.read(args.config, args.debug)
        ctx = zmq.asyncio.Context()
    except ConfigError as e:
        logger.error(e)
        raise SystemExit(2) from e

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
                    logger.info(f"forgot room {args.forget_room}")

    except asyncio.CancelledError:
        logger.info("Cancelled")

    except (ClientConnectionError, ServerDisconnectedError):
        logger.warning("Unable to connect to homeserver, retrying in 15s...")
        sleep(15)


def main():
    while True:
        try:
            asyncio.run(
                async_main()
            )
        except KeyboardInterrupt:
            logger.warning("C-c was passed, exiting..")
            raise SystemExit(1)
        except Exception as e:
            # staying alive!
            logger.exception(e)
            sleep(4.20)
            logger.info("TEST")
