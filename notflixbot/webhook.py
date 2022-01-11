import json

from loguru import logger
from aiohttp.web import json_response, middleware, post, get
from aiohttp.web import Application, AppRunner, TCPSite
from aiohttp.web import HTTPException, HTTPForbidden
import zmq.asyncio


class Webhook:

    def __init__(self, config, ctx):
        self.host = "localhost"
        self.port = config.webhook_port
        self.tokens = config.webhook_tokens

        self._context = ctx
        self._socket = self._context.socket(zmq.PAIR)
        self._socket.connect("inproc://webhook")

        self._app = Application(
            middlewares=[self._middleware]
        )
        self._setup_routes()

    async def _logger(self, request, response_status):
        status = int(response_status)
        if status in range(500, 600):
            level = "error"
        elif status in range(400, 500):
            level = "warning"
        else:
            level = "info"

        json_log = json.dumps({
            'remote': request.remote,
            'host': request.host,
            'forwarded': request.forwarded,
            'path_qs': request.path_qs,
            'method': request.method
        })
        logger.log(level.upper(), json_log)

    @middleware
    async def _middleware(self, request, handler):
        try:
            response = await handler(request)
            await self._logger(request, 200)
            return response
        except HTTPException as ex:
            await self._logger(request, ex.status)
            return json_response({'reason': ex.reason, 'status': ex.status})

    def _setup_routes(self):
        self._app.add_routes([
            # not an f-string, parameterized input in aiohttp
            post("/_webhook", self._handle_webhook_json_token),
            post("/_webhook/", self._handle_webhook_json_token),
            post("/_webhook/{token}", self._handle_webhook_url_token),
            get("/_webhook/ruok", self._handle_ruok),
        ])

    def _validate_token(self, token):
        try:
            # dict lookup is o(1) so no timing attacks from string comapares
            # otherwise: hmac.secure_compare
            return self.tokens[token]
        except KeyError:
            raise HTTPForbidden

    async def _handle_ruok(self, request):
        return json_response({'ruok': 'iamok'})

    async def _handle_webhook_json_token(self, request):
        w_data = await request.json()
        token = w_data['token']
        room = self._validate_token(token)
        await self._send(request, w_data, room)
        return json_response("ok")

    async def _handle_webhook_url_token(self, request):
        token = request.match_info.get('token', None)
        room = self._validate_token(token)
        w_data = await request.json()
        await self._send(request, w_data, room)
        return json_response("ok")

    async def _send(self, request, w_data, room):
        print(json.dumps(w_data, indent=2))

        m_data = json.dumps({
            'room': room,
            'msg': w_data.get('text', "")
        })
        await self._socket.send_string(m_data)

    async def serve(self):
        runner = AppRunner(self._app)
        await runner.setup()
        site = TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f'webhook listening on http://{self.host}:{self.port}')
