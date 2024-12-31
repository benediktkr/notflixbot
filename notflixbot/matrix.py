import asyncio
import getpass
import json
import time

import aiohttp.client_exceptions
import click
import zmq.asyncio
from loguru import logger
from markdown import markdown
from nio import AsyncClient, AsyncClientConfig, InviteMemberEvent, JoinError
from nio import LoginError, MatrixRoom, MegolmEvent, ProfileSetAvatarError
from nio import RoomMemberEvent, RoomMessageText, RoomResolveAliasError
from nio.crypto import TrustState
from nio.exceptions import OlmUnverifiedDeviceError
from nio.responses import WhoamiError

from notflixbot import version_dict
from notflixbot.emojis import ROBOT
from notflixbot.errors import ImdbError, MatrixError, NotflixbotError
from notflixbot.notflix import Notflix
from notflixbot.youtube import Youtube


class MatrixClient:

    @staticmethod
    def catch(f):
        async def inner(*args, **kwargs):
            try:
                return await f(*args, **kwargs)
            except NotflixbotError as e:
                logger.error(e)
                raise SystemExit(2)
            except click.exceptions.Abort:
                logger.warning("user aborted")
                raise SystemExit(1)

        return inner

    def __init__(self, config, ctx):
        self.config = config
        self.homeserver = config.homeserver
        self.user_id = config.user_id

        self.admin_room_ids = list()
        try:
            self._default_room = self.config.rooms[0]
            logger.info(f"default room: {self._default_room}")
        except KeyError:
            self._default_room = None
            logger.warning("no rooms in config, default_room not set")

        self._context = ctx
        self._socket = self._context.socket(zmq.PAIR)
        self._socket.bind("inproc://webhook")
        self._poller = zmq.asyncio.Poller()
        self._poller.register(self._socket, zmq.POLLIN)

        self.nio = AsyncClient(self.homeserver, self.user_id)
        self.cmd_handlers = dict()
        self.help_text = dict()
        self._callbacks()
        self._cmd_handlers()

        self.notflix = Notflix(config.notflixbot)
        self.youtube = Youtube(config.notflixbot)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self.nio.logged_in:
            if self._default_room is not None:
                await self.send_msg(self._default_room, "❌ shutting down")
        await self.nio.close()
        logger.info("exited.")

    async def restore_login(self):
        if self.config.creds is not None:
            logger.warning(f"file exists: '{self.config.credentials_path}'")
            if not click.confirm("overwrite?"):
                logger.info("doig nothing and exiting")
                raise SystemExit(1)
        passwd = getpass.getpass()
        return await self._login(passwd)

    async def auth(self):
        if self.config.creds is None:
            logger.error(
                "no stored credentials found, please run with --restore-login")
            raise SystemExit

        logger.debug(f"connecting to '{self.config.homeserver}'")
        await self._set_creds()

        whoami = await self.nio.whoami()
        if isinstance(whoami, WhoamiError):
            # whoami.status_code ("M_UNKNOWN_TOKEN")
            # whoami.message ("Invalid macaroon passed.")
            raise MatrixError(whoami)
        else:
            logger.info(f"matrix bot running as {self.nio.user_id}")

    async def sync_forever(self):
        """this starts the event loop, and does the first sync, which
        unblocks self._after_first_sync.

        but we cant call self._after_first_sync here because then it is
        blocked and waiting for the first iteration of the sync loop to start
        """
        logger.info("matrix client syncing forever")
        while True:
            try:
                return await self.nio.sync_forever(
                    timeout=3000, full_state=True)
            except (
                    asyncio.exceptions.TimeoutError,
                    aiohttp.client_exceptions.ClientOSError
            ) as e:
                logger.error(e)
                logger.error("timed out, reconnecting after 10s..")
                time.sleep(10.0)

    async def start(self):
        if not self.nio.logged_in:
            await self.auth()

        await asyncio.gather(
            # order is important here, _after_first_sync awaits for first sync
            # then the rest is executed
            self._after_first_sync(),

            asyncio.get_event_loop().create_task(
                self.nio.sync_forever(timeout=3000, full_state=True)
            ))

    async def webhook_poller(self):
        logger.info("polling zmq socket")
        while True:
            # keyboard interrupt?
            events = await self._poller.poll(3000)
            if self._socket in dict(events):
                z_data = await self._socket.recv_string()
                m_data = json.loads(z_data)

                room = m_data['room']
                msg = m_data['msg']
                plain = m_data.get('plain')
                logger.debug(f"{room}: '{msg}'")

                await self.send_msg(room, msg, plain)

    async def _room_id(self, room_addr):
        if room_addr.startswith('!'):
            # this is a room_id
            return room_addr

        room = await self.nio.room_resolve_alias(room_addr)
        if isinstance(room, RoomResolveAliasError):
            raise MatrixError(f"cannot resolve: '{room_addr}'")

        return room.room_id

    async def _after_first_sync(self):
        # wait for sync
        await self.nio.synced.wait()

        joined = await self.nio.joined_rooms()
        for room_id in joined.rooms:
            await self._trust_all_users_in_room(room_id)

        for room_alias in self.config.admin_rooms:
            admin_room_id = await self._room_id(room_alias)
            self.admin_room_ids.append(admin_room_id)

        if self.config.avatar:
            await self._avatar()

        if self._default_room is not None:
            msg = f"{ROBOT} `{version_dict['name']} {version_dict['version']}`"
            await self.send_msg(self._default_room, msg)

        await self._key_sync()
        logger.debug("first sync is done")

    async def _set_creds(self):
        self.nio.user_id = self.config.creds.user_id
        self.nio.access_token = self.config.creds.access_token
        self.nio.device_id = self.config.creds.device_id
        self.nio.store_path = self.config.storage_path
        self.nio.config = AsyncClientConfig(
            max_limit_exceeded=0,
            max_timeouts=0,
            store_sync_tokens=True,
            encryption_enabled=True,
        )
        self.nio.load_store()

    async def _avatar(self):
        avatar = await self.nio.set_avatar(self.config.avatar)

        if isinstance(avatar, ProfileSetAvatarError):
            logger.warning(f"error setting avatar: {avatar}")
        else:
            logger.debug("set avatar")

    def _cmd_handlers(self):
        self.cmd_handlers['!add'] = self._handle_add
        self.help_text["!add"] = "usage: `!add $IMDB_URL`"
        self.cmd_handlers['!ruok'] = self._handle_ruok
        self.help_text['!ruok'] = "check if the bot is ok"
        self.cmd_handlers['!whoami'] = self._handle_whoami
        self.help_text['!whoami'] = "show your user id"
        self.cmd_handlers['!key_sync'] = self._key_sync
        self.help_text["!key_sync"] = "force a key sync"
        self.cmd_handlers['!help'] = self._handle_help
        self.help_text["!help"] = "this message"
        self.cmd_handlers['!crash'] = self._handle_crash

    def _callbacks(self):
        self.nio.add_event_callback(
            self._cb_invite_filtered, (InviteMemberEvent,))
        self.nio.add_event_callback(self._cb_message, (RoomMessageText,))
        self.nio.add_event_callback(self._cb_room_member, (RoomMemberEvent,))
        self.nio.add_event_callback(self._cb_decryption_fail, (MegolmEvent,))

    async def _key_sync(self, room=None, event=None):
        if self.nio.should_upload_keys:
            resp_upload = await self.nio.keys_upload()
            logger.info(f"uploaded keys: {resp_upload}")
            if room is not None:
                await self.send_msg(room.room_id, resp_upload)

        if self.nio.should_query_keys:
            logger.warning(
                f"should query keys for: {self.nio.users_for_key_query}")
            resp_query = await self.nio.keys_query()
            logger.info(f"queried for keys: {resp_query}")
            if room is not None:
                await self.send_msg(room.room_id, resp_query)

        if self.nio.should_claim_keys:
            # for user in self.nio.get_users_for_key_claiming():
            # resp_claim = await self.nio.keys_claim(user) # noqa
            resp_claim = await self.nio.keys_claim()
            logger.warning("claimed keys: '{resp_claim}'")
            if room is not None:
                await self.send_msg(room.room_id, resp_claim)

        if room is not None and event is not None:
            await self.send_msg(room.room_id, "key sync: `ok`")

    async def _login(self, passwd):
        try:
            resp = await self.nio.login(
                passwd,
                device_name=self.config.device_name
            )
            if isinstance(resp, LoginError):
                logger.error(f"failed to login: '{resp.message}'")
                raise MatrixError(resp.message)

            creds = {
                "user_id": resp.user_id,
                "device_id": resp.device_id,  # 10 uppercase letters
                "access_token": resp.access_token
            }
            self.config.update_creds(creds)
            logger.success(resp)
            return True
        except aiohttp.client_exceptions.ClientError as e:
            raise MatrixError(repr(e))

    async def _trust_all_users_in_room(self, room):
        room_id = await self._room_id(room)
        members = await self.nio.joined_members(room_id)
        for u in members.members:
            await self._trust_user_devices(u.user_id)

    async def _trust_user_devices(self, user_id):
        if user_id != self.config.user_id and self.config.autotrust:
            for dev_id, olm_device in self.nio.device_store[user_id].items():
                if olm_device.trust_state != TrustState.verified:
                    self.nio.verify_device(olm_device)
                    logger.info(f"trusting {dev_id} from user {user_id}")
                else:
                    logger.debug(f"already trust {dev_id} from user {user_id}")

    async def _cb_decryption_fail(self, room: MatrixRoom, event: MegolmEvent) -> None:
        red_x_and_lock_emoji = "❌ 🔐"
        logger.warning(f"unable to decrypt message from {event.sender}")
        await self.react_to_event(room, event.event_id, red_x_and_lock_emoji)

    async def _cb_room_member(self, room: MatrixRoom,
                              event: RoomMemberEvent) -> None:
        if event.content['membership'] == "join":
            if event.state_key == self.nio.user_id:
                # we joined a room
                logger.debug("room member event")
                await self._trust_all_users_in_room(room.room_id)

    async def _cb_invite(self, room: MatrixRoom,
                         event: InviteMemberEvent) -> None:
        """for when an invite is received, join the room specified in the invite
        """
        logger.debug(f"got invite to {room.room_id} from {event.sender}")

        result = await self.nio.join(room.room_id)
        if isinstance(result, JoinError):
            logger.error(f"error joining room {room.room_id}: {result}.")
        else:
            logger.info(
                f"joined {room.canonical_alias} invited by {event.sender}")

    async def _cb_invite_filtered(self, room: MatrixRoom,
                                  event: InviteMemberEvent) -> None:
        """InviteMemberEvent is fired for every m.room.member state received
        in a sync response's `rooms.invite` section. so we will get
        some that are not our own invite events (f.ex. inviter's
        membership).

        this ignores them and calls Callbacks.invite
        with our own invite events.

        """
        if event.state_key == self.nio.user_id:
            await self._cb_invite(room, event)
        else:
            logger.debug(f"ignoring invite event: {event}")

    async def _cb_message(self, room: MatrixRoom,
                          event: RoomMessageText) -> None:

        # ignore messages from ourselves
        if event.sender == self.nio.user_id:
            return

        # user_displayname  = room.user_name(event.sender)
        # display_name = room.display_name
        user_id = event.sender
        room_id = room.room_id
        if room.canonical_alias is not None:
            room_alias = room.canonical_alias
        else:
            room_alias = room.room_id

        msg = event.body.strip()
        # logger.debug(f"room: {room_id}, user_id: {user_id}, msg: '{msg}'")

        # "".split(" ")[0] -> ""
        cmd = event.body.strip().split(' ')
        prefix = cmd[0]

        if prefix in self.cmd_handlers:
            if room_id not in self.admin_room_ids:
                logger.warning(
                    f"ignored cmd '{msg}' by {user_id} in {room_alias}")
            else:
                handler_func = self.cmd_handlers[prefix]
                await handler_func(room, event)

        elif "youtube.com" in msg or "youtu.be" in msg:
            yt_unfurl = await self.youtube.unfurl(msg)
            if yt_unfurl is not None:
                yt_msg = yt_unfurl[0]
                yt_plain = yt_unfurl[1]
                await self.send_msg(room.room_id, yt_msg, yt_plain)
        else:
            await self._phrase_respond(room, event)

    async def _phrase_respond(self, room, event):
        phrases = {
            'are you alive?': 'no im a `robot`',
            'are you alive': 'no im a `robot`',
            'i am a robot': 'FILTHY LIES',
            "i'm a robot": 'FILTHY LIES',
            'im a robot': 'FILTHY LIES',
            'fuck you': '🖕',
            'duck you': '🦆',
        }
        # keywords = {
        #     'cheese': 'did someone say 🧀?'
        # }
        msg = event.body.strip().lower()
        response = phrases.get(msg, None)
        if response is not None:
            await self.send_msg(room.room_id, response)

    async def _handle_help(self, room, event):
        cmds = "<br>".join([f"`{k}`: {v}" for k, v in self.help_text.items()])
        n = version_dict['name']
        v = version_dict['version']
        await self.send_msg(room.room_id, f"`{n} v{v}` help: \n\n{cmds}")

    async def _handle_whoami(self, room, event):
        your_id = event.sender
        my_id = self.config.creds.user_id
        await self.send_msg(
            room.room_id, f"i am: `{my_id}` and you are: `{your_id}`")

    async def _handle_ruok(self, room, event):
        await self.send_msg(room.room_id, "`iamok`")

    async def _handle_crash(self, room, event):
        # CRASH AND BURN
        return 1 / 0

    async def _handle_add(self, room, event):
        try:
            msg = event.body.strip().split(' ')
            url = msg[1].strip()
            try:
                user = event.sender.split(":")[0][1:]
            except IndexError as e:
                logger.error(f"error parsing user_id '{event.sender}': {e}")
                user = "unknown"
            added_status, item = self.notflix.add_from_imdb_url(url, user)
            if added_status == "added":
                await self.send_msg(
                    room.room_id,
                    f"added: {item['title']} ({item['release_year']})")
            elif added_status == "exists":
                await self.send_msg(
                    room.room_id,
                    f"already exists: {item['title']} ({item['release_year']})")
            else:
                try:
                    errmsg = item[0]['errorMessage']
                    await self.send_msg(room.room_id, errmsg)
                except (IndexError, KeyError):
                    pass

            return item
        except IndexError:
            logger.error(f"invalid msg from {event.sender}: '{event.body}'")
            self.send_msg(room.room_id, "url is missing")
        except (NotflixbotError, ImdbError) as e:
            logger.warning(e)
            await self.send_msg(room.room_id, str(e))

    async def send_msg(self, room, msg, plain=None):
        """wrapper function to handle exceptions cleanly
        """

        try:
            return await self._send_msg(room, msg, plain)
        except OlmUnverifiedDeviceError as e:
            logger.warning(e)
            # self.nio.verify_device(e.devide)
            await self._trust_user_devices(e.device.user_id)
            return await self._send_msg(room, msg, plain)

    async def _send_msg(self, room, msg, plain=None):
        # msgtypes:
        #  * m.notice: looks more grey?
        #  * m.text: normal?
        #  * m.room.message: no markdown

        if msg is None:
            msg = ""

        if plain is None:
            plain = msg

        # strip away simple markdown that i use most commonly
        plain = plain.replace('`', '')

        try:
            room_id = await self._room_id(room)
        except MatrixError as e:
            # webhook isnt aware of this
            logger.error(e)
            return

        await self.nio.room_send(
            room_id,
            message_type="m.room.message",
            content={
                'msgtype': 'm.text',
                'format': 'org.matrix.custom.html',
                'formatted_body': markdown(msg),
                'body': plain
            },
            ignore_unverified_devices=False
        )

        logger.debug(f"sent '{msg}' to '{room_id}'")

    async def react_to_event(self, room, event, reaction_text):
        await self.nio.room_send(
            room.room_id,
            message_type="m.reaction",
            content={
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": event.event_id,
                    "key": reaction_text
                }
            },
            ignore_unverified_devices=False
        )


def markdown_json(msg):
    return "\r\n".join(
        [f"    {a}" for a in json.dumps(msg, indent=2).splitlines()]
    )


def make_pill(user_id):
    return f'<a href="https://matrix.to/#/{user_id}">{user_id}</a>'


"""
from nio import SyncResponse

self.nio.add_response_callback(self._cb_sync, SyncResponse)

async def _cb_sync(self, response: SyncResponse) -> None:
    # called every time `sync_forever` sucessfully syncs with the server
    logger.trace(f"synced: {response}")
"""
