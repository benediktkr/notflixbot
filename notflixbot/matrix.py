import asyncio
import aiohttp.client_exceptions
import click
import getpass

from loguru import logger
from markdown import markdown
from nio import AsyncClient, AsyncClientConfig, InviteMemberEvent, MatrixRoom
from nio import RoomMessageText, SyncResponse, ProfileSetAvatarError
from nio import LoginError, JoinError
from nio.responses import WhoamiError
from nio.crypto import TrustState

from notflixbot.errors import NotflixbotError, MatrixError


class MatrixClient:

    @classmethod
    def run_async(cls, config, args):
        async def _run_aclient(config, args):
            try:
                m = await cls._init(config, args)

                if args.restore_login:
                    return await m.restore_login()
                else:
                    await m.wait_forever()

            except NotflixbotError as e:
                logger.error(e)
                raise SystemExit(2)
            finally:
                await m.close()

        try:
            asyncio.run(_run_aclient(config, args))

        except asyncio.CancelledError:
            logger.debug("Cancelled")
        except KeyboardInterrupt:
            logger.debug("C-c")
            raise SystemExit(1)

    @classmethod
    async def _init(cls, config, args):
        _m = cls()
        _m.config = config
        _m.homeserver = config.homeserver
        _m.user_id = config.user_id
        _m.args = args
        _m.nio = AsyncClient(_m.homeserver, _m.user_id)
        _m.cmd_handlers = dict()
        return _m

    async def close(self):
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

    async def wait_forever(self):
        if self.config.creds is None:
            logger.error(
                "no stored credentials found, please run with --restore-login")
            raise SystemExit

        logger.debug(f"connecting to '{self.config.homeserver}'")
        self._callbacks()
        self._cmd_handlers()
        await self._set_creds()
        await self._key_sync()
        if self.config.avatar:
            await self._avatar()

        after_first_sync_task = asyncio.create_task(self._after_first_sync())
        sync_forever_task = asyncio.create_task(self._sync_forever())

        await asyncio.gather(
            # order is important here
            after_first_sync_task,
            sync_forever_task
        )

    async def _room_id(self, room_addr):
        if room_addr.startswith('!'):
            # this is a room_id
            return room_addr

        room = await self.nio.room_resolve_alias(room_addr)
        return room.room_id

    async def _sync_forever(self):
        await self.nio.sync_forever(timeout=30000, full_state=True)

    async def _after_first_sync(self):
        await self.nio.synced.wait()

        joined = await self.nio.joined_rooms()
        for room_id in joined.rooms:
            await self._trust_all_users_in_room(room_id)

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

        whoami = await self.nio.whoami()
        if isinstance(whoami, WhoamiError):
            # whoami.status_code ("M_UNKNOWN_TOKEN")
            # whoami.message ("Invalid macaroon passed.")
            raise MatrixError(whoami)

    async def _avatar(self):
        avatar = await self.nio.set_avatar(self.config.avatar)

        if isinstance(avatar, ProfileSetAvatarError):
            logger.warning(f"error setting avatar: {avatar}")
        else:
            logger.debug("set avatar")

    def _cmd_handlers(self):
        self.cmd_handlers['ruok'] = self._handle_ruok
        self.cmd_handlers['whoami'] = self._handle_whoami
        self.cmd_handlers['key_sync'] = self._key_sync

    def _callbacks(self):
        self.nio.add_event_callback(
            self._cb_invite_filtered, (InviteMemberEvent,))
        self.nio.add_event_callback(self._cb_message, (RoomMessageText,))
        self.nio.add_response_callback(self._cb_sync, SyncResponse)

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

    async def _trust_all_users_in_room(self, room_id):
        members = await self.nio.joined_members(room_id)
        for u in members.members:
            return await self._trust_user_devices(u.user_id)

    async def _trust_user_devices(self, user_id):
        if user_id != self.config.user_id and self.config.autotrust:
            for dev_id, olm_device in self.nio.device_store[user_id].items():
                if olm_device.trust_state != TrustState.verified:
                    self.nio.verify_device(olm_device)
                    logger.info(f"trusting {dev_id} from user {user_id}")
                else:
                    logger.debug(f"already trust {dev_id} from user {user_id}")

    async def _cb_sync(self, response: SyncResponse) -> None:
        """called every time `sync_forever` sucessfully syncs with the server
        """
        logger.trace(f"synced: {response}")

    async def _cb_invite(self, room: MatrixRoom,
                         event: InviteMemberEvent) -> None:
        """for when an invite is received, join the room specified in the invite
        """

        result = await self.nio.join(room.room_id)
        # room.names <- list of users in room
        logger.debug(f"got invite to {room.room_id} from {event.sender}")

        if isinstance(result, JoinError):
            logger.error(f"error joining room {room.room_id}: {result}.")
        logger.info(f"joined {room.room_id}, invited by {event.sender}")

        joined = await self.nio.joined_members(room.room_id)
        for u in joined.members:
            await self._trust_user_devices(u.user_id)

        await self.nio.room_send(
            room.room_id,
            message_type="m.room.message",
            content={
                'msgtype': 'm.text',
                'body': 'beep beep'
            },
            ignore_unverified_devices=False
        )

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
        msg = event.body
        logger.debug(f"room: {room_id}, user_id: {user_id}, msg: '{msg}'")

        # "".split(" ")[0] -> ""
        cmd = event.body.strip().split(' ')
        prefix = cmd[0]

        handler_name = self.config.cmd_prefixes.get(prefix, None)
        if handler_name is not None:
            handler_func = self.cmd_handlers[handler_name]
            await handler_func(room, event)
        else:
            await self._phrase_respond(room, event)

    async def _phrase_respond(self, room, event):
        phrases = {
            'are you alive?': 'no im a `robot`'
        }
        msg = event.body.strip()
        response = phrases.get(msg, None)
        if response is not None:
            await self.send_msg(room.room_id, response)

    async def _handle_whoami(self, room, event):
        your_id = event.sender
        my_id = self.config.creds.user_id
        await self.send_msg(
            room.room_id, f"i am: `{my_id}` and you are: `{your_id}`")

    async def _handle_ruok(self, room, event):
        await self.send_msg(room.room_id, "`iamok`")

    async def send_msg(self, room, msg):
        # msgtypes:
        #  * m.notice: looks more grey?
        #  * m.text: normal?
        #  * m.room.message: no markdown

        room_id = await self._room_id(room)
        await self.nio.room_send(
            room_id,
            message_type="m.room.message",
            content={
                'msgtype': 'm.notice',
                'format': 'org.matrix.custom.html',
                'formatted_body': markdown(msg),
                'body': msg
            },
            ignore_unverified_devices=False
        )

        logger.debug(f"sent '{msg}' to '{room_id}'")
