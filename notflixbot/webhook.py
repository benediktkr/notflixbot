import json
from urllib.parse import urljoin
from collections import defaultdict

from loguru import logger
from aiohttp.web import json_response, middleware, post, get
from aiohttp.web import Application, AppRunner, TCPSite
from aiohttp.web import HTTPException, HTTPForbidden, HTTPBadRequest
from aiohttp import BasicAuth
import zmq.asyncio

from notflixbot.matrix import markdown_json
from notflixbot.emojis import TV_EPISODE, TV_SEASON, MOVIE, VIDEO, PERSON
from notflixbot.emojis import OK, WARNING, FOLDER


class Webhook:

    def __init__(self, config, ctx):
        self.host = config.webhook_host
        self.port = config.webhook_port
        self.tokens = config.webhook_tokens
        self.base_url = config.webhook_base_url

        self._last_msg = defaultdict(str)
        if len(config.admin_rooms) > 1 and config._debug_arg:
            self._debug_room = config.admin_rooms[1]
        else:
            self._debug_room = None

        self._context = ctx
        self._socket = self._context.socket(zmq.PAIR)
        self._socket.connect("inproc://webhook")

        self._app = Application(
            middlewares=[
                self._middleware_access_log,
                self._middleware_errors,
                self._middleware_json,
                self._middleware_auth,
                self._middleware_debug_msg
            ]
        )
        self._app.on_shutdown.append(self._on_shutdown)
        self._setup_routes()

    def _setup_routes(self):
        def url(url):
            # adds base url
            return urljoin(self.base_url, url)

        self._app.add_routes([
            # not an f-string, parameterized input in aiohttp
            post(url("incoming/{token}"), self._handle_incoming),
            post(url("incoming"), self._handle_incoming),
            post(url("radarr"), self._handle_radarr),
            post(url("jellyfin"), self._handle_jellyfin),
            post(url("jellyfin/{token}"), self._handle_jellyfin),
            post(url("grafana"), self._handle_grafana),
            get(url("ruok"), self._handle_ruok),
        ])

    async def _on_shutdown(self, app):
        # doesnt work
        # gets triggered by
        #   await runner.cleanup()
        logger.info("http server shutdown")

    @middleware
    async def _middleware_access_log(self, request, handler):
        # request.remote
        # request.host
        # request.forwarded
        # request.path_qs
        # request.method
        # response_status

        response = await handler(request)
        if response is None:
            response = json_response("ok")

        status = response.status
        remote = request.remote
        method = request.method
        path_qs = request.path_qs

        if path_qs == urljoin(self.base_url, "ruok"):
            level = "DEBUG"
        elif status in range(500, 600):
            level = "ERROR"
        elif status in range(400, 500):
            level = "WARNING"
        else:
            level = "SUCCESS"

        logger.bind(access_log=True).log(
            level, f"{remote} - {method} - {path_qs} - {status}")

        return response

    @middleware
    async def _middleware_errors(self, request, handler):
        try:
            response = await handler(request)
            return response
        except HTTPException as ex:
            return json_response(
                {'reason': ex.reason, 'status': ex.status},
                status=ex.status
            )
        except Exception as e:
            logger.exception(e)
            # a JSONDecodeError would get caught by _middleware_json
            # which would raise a HTTPBadRequest
            # j = json.dumps(request['json'], indent=2)

            return json_response(
                {'reason': 'internal server error', 'status': 500},
                status=500
            )

    @middleware
    async def _middleware_json(self, request, handler):
        try:
            request['json'] = await request.json()
            response = await handler(request)
            return response
        except json.decoder.JSONDecodeError as e:
            body = await request.read()
            logger.error(f"json: {e}: \n{body.decode()}")
            raise HTTPBadRequest(reason="json decoding error")

    @middleware
    async def _middleware_auth(self, request, handler):
        """ways of authenticating:
        1. basic auth in Authorization header (username ignored)
        2. token in Webhook-Token header
        3. a 'token' key in json payload
        4. in the url /path/webhook/{token}
             (needs a rooute in _add_routes to work)

        """

        if request.path_qs == urljoin(self.base_url, "ruok"):
            return await handler(request)

        if 'Authorization' in request.headers:
            auth = BasicAuth.decode(request.headers['Authorization'])
            token = auth.password
        elif 'Webhook-Token' in request.headers:
            token = request.headers['Webhook-Token']
        elif 'token' in request['json']:
            token = request['json']['token']
        elif 'token' in request.match_info:
            token = request.match_info['token']
        else:
            raise HTTPForbidden

        token_room = self._validate_token(token)
        if request.query.get('room'):
            request['room'] = request.query['room']
        elif request['json'].get('room'):
            request['room'] = request['json']['room']
        else:
            request['room'] = token_room

        if not request.get('room'):
            raise HTTPBadRequest

        response = await handler(request)
        return response

    def _validate_token(self, token):
        """returns a room_alias or room_id to post messages to
        rasies a HTTPForbidden if token is not valid
        """
        try:
            # dict lookup is o(1) so no timing attacks from string comapares
            # otherwise: hmac.secure_compare
            return self.tokens[token]
        except KeyError:
            raise HTTPForbidden

    @middleware
    async def _middleware_debug_msg(self, request, handler):
        if self._debug_room is not None:
            await self._debug_msg(request)

        return await handler(request)

    async def _debug_msg(self, request):
        msg = markdown_json(request['json'])
        await self._send(self._debug_room, msg)

    async def _handle_ruok(self, request):
        return json_response({'ruok': 'iamok'})

    async def _handle_incoming(self, request):
        """following the slack webhook request format
        """
        try:
            j = request['json']
            if j.get('prefix') is not None:
                text = f"`[{j['prefix']}]` {j['text']}"
            else:
                text = j['text']

            await self._send(request['room'], text)
            return json_response("ok")

        except KeyError:
            raise HTTPBadRequest

    async def _handle_radarr(self, request):
        """
        eventType:
         - test
         - grab
         - download
        """

        event_type = request['json']['eventType'].lower()
        if event_type == "test":
            msg = f"{OK} radarr webhook test"
            logger.success(f"{msg} for {request['room']}")
            await self._send(request['room'], msg)
            return True

        if event_type == "download":
            movie = request['json']['movie']
            msg = f"{MOVIE} {movie['title']} ({movie['year']})"
            await self._send(request['room'], msg)

        elif event_type == "grab":
            movie = request['json']['movie']
            msg = f"{FOLDER} downloading '{movie['title']} ({movie['year']})'"
            await self._send(request['room'], msg)

        return json_response("ok")

    async def _handle_grafana(self, request):
        j = request['json']

        state = j['state']
        name = j['ruleName']
        u = j['ruleUrl']
        if 'message' in j:
            m = f"\n> {j['message']}\n\n"
        else:
            m = ""

        if len(j.get('evalMatches', [])) > 0:
            matches = []

            for item in j['evalMatches']:
                value = item['value']
                if isinstance(value, float):
                    v = f"{value:.3f}"
                else:
                    v = value
                matches.append(f'"{item["metric"]}": {v}')
                tags = item.get('tags', dict())
                if tags is not None and len(tags) > 0:
                    for k, v in tags.items():
                        matches.append(f'  {k}: "{v}"')

            mv_code = "\n".join(matches)
            mv = f"<pre><code>{mv_code}</code></pre>"
        else:
            mv = ""

        if state == "ok":
            emoji = OK
        else:
            emoji = WARNING

        msg = f"{emoji} grafana: <u>[{name}]({u})</u> {mv} {m}"
        plain = f"{emoji} {name}"

        await self._send(request['room'], msg, plain)

    async def _handle_jellyfin(self, request):
        """
        notifications types that dont trigger:
         - AuthenticationFailure
         - AuthenticationSuccess

        see: https://github.com/jellyfin/jellyfin-plugin-webhook/issues/25
        """

        urlpath = "/web/index.html#!/details?id="
        notification_type = request['json']['NotificationType']
        if notification_type == "Generic":
            msg = request['json']['Name']
            # ignore this
            return json_response("ok")

        j = request['json']

        if notification_type == "PlaybackStart":
            host = j['ServerUrl']
            itemid = j['ItemId']

            url = urljoin(host, urlpath) + itemid
            user = j['NotificationUsername']
            device = j['DeviceName']
            client = j['ClientName']
            name = j['Name']
            if j['ItemType'] == "Episode":
                prefix = f"{j['SeriesName']} - "
            else:
                prefix = ""
            msg = f"{VIDEO} `{user}` is playing [_{prefix}{name}_]({url}) from {device} ({client})" # noqa
            plain = msg.replace(
                "playing _", "playing ").replace("_ from", " from")
            await self._send(request['room'], msg, plain, not_again=True)

        elif notification_type == "SessionStart":
            user = j['NotificationUsername']
            device = j['DeviceName']
            client = j['Client']

            msg = f"{PERSON} `{user}` is online from {device} ({client})"
            await self._send(request['room'], msg, not_again=True)

        elif notification_type == "UserCreated":
            user = j['NotificationUsername']

            msg = f"{PERSON} user creted: `{user}`"
            await self._send(request['room'], msg)
        elif notification_type == "ItemAdded" and j['ItemType'] == "Movie":
            host = j['ServerUrl']
            itemid = j['ItemId']

            name = j['Name'].strip()
            if name.endswith(')'):
                # the year is in the title
                # years are 4 digits + 2 parenthesis = 6
                title = name[:-6].strip()
            else:
                title = name.strip()

            url = urljoin(host, urlpath) + itemid
            msg = f"{MOVIE} [{title}]({url}) ({j['Year']})"
            plain = f"{MOVIE} {title} ({j['Year']})"
            await self._send(request['room'], msg, plain)

        elif notification_type == "ItemAdded" and j['ItemType'] == "Episode":
            host = j['ServerUrl']
            itemid = j['ItemId']
            series = j['SeriesName']
            SE = f"S{j['SeasonNumber00']}E{j['EpisodeNumber00']}"

            url = urljoin(host, urlpath) + itemid
            msg = f"{TV_EPISODE} {series}: [{SE}]({url})"
            plain = f"{TV_EPISODE} {series} {SE}"
            await self._send(request['room'], msg, plain)

        elif notification_type == "ItemAdded" and j['ItemType'] == "Season":
            host = j['ServerUrl']
            itemid = j['ItemId']
            series = j['SeriesName']
            # example: Season 2
            name = j['Name']

            url = urljoin(host, urlpath) + itemid
            msg = f"{TV_SEASON} {series}: [{name}]({url})"
            plain = f"{TV_EPISODE} {series}: {name}"
            await self._send(request['room'], msg, plain)

        return json_response("ok")

    async def _send(self, room, msg, plain=None, not_again=False):
        if msg is None:
            msg = ""
        if msg == self._last_msg[room] and not_again:
            logger.warning(
                f"ignoring, '{msg[:15]}..' is same as last in {room}")
            return False
        else:
            z_data = json.dumps({
                'room': room,
                'msg': msg,
                'plain': plain,
                'message_type': 'm.room.message'
            })
            await self._socket.send_string(z_data)
            self._last_msg[room] = msg
            return True

    async def serve(self):
        runner = AppRunner(self._app)
        await runner.setup()
        site = TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f'webhook listening on http://{self.host}:{self.port}')
