import argparse
import asyncio

from loguru import logger
import zmq.asyncio

from notflixbot.errors import ConfigError
from notflixbot.config import Config
from notflixbot.matrix import MatrixClient
from notflixbot.webhook import Webhook

COMMANDS = [
    ("serve", "start matrix bot"),
    ("restore_login", "new matrix session")
]


def get_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    subparser = parser.add_subparsers(dest='subcmd', metavar='subcmd')
    subparser.required = True

    parser.add_argument("-c", "--config",
                        help="path to config file", default="config.json")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="print debug output")

    subparser.add_parser("start", help="start matrix bot")
    subparser.add_parser("restore_login", help="start new matrix session")
    subparser.add_parser("webhook", help="start webhook http server")

    nio_parser = subparser.add_parser("nio",
                                      help="low-level stuff, helpful for dev")
    nio_parser.add_argument("--forget-room", type=str, required=True,
                            help="canonical_alias or room_id")

    # parser.parse_args('start --debug'.split())
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
                    # order is important here
                    matrix._after_first_sync(),
                    asyncio.get_event_loop().create_task(
                        matrix.nio.sync_forever(timeout=3000, full_state=True)
                    ),
                    asyncio.get_event_loop().create_task(
                        matrix.zmq_poller()
                    ),
                    asyncio.get_event_loop().create_task(
                        webhook.serve()
                    )
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
        logger.debug("Cancelled")


def main():
    try:
        asyncio.get_event_loop().run_until_complete(
            async_main()
        )
    except KeyboardInterrupt:
        logger.debug("C-c was passed..")
        raise SystemExit(1)
