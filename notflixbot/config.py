import json
import operator
import os
import sys
from functools import reduce
from json.decoder import JSONDecodeError

from loguru import logger

from notflixbot.errors import ConfigError


class Config(object):

    @classmethod
    def read(cls, path, debug_arg=False):
        try:
            with open(path, 'r') as f:
                config_json = f.read()
            return cls.from_json(config_json, path, debug_arg)
        except FileNotFoundError as e:
            msg = f"config file not found: '{path}'"
            raise ConfigError(msg) from e

    @classmethod
    def from_json(cls, jsonstr, path, debug_arg=False):
        try:
            config_dict = json.loads(jsonstr)
            return cls(config_dict, path, debug_arg)
        except JSONDecodeError as e:
            # e.colno, e.pos
            msg = f"invalid json in '{path}' on L{e.lineno}: {e.msg}"
            raise ConfigError(msg) from e

    def __init__(self, config_dict, config_path, debug_arg=False):
        self._config_dict = config_dict
        self._config_path = config_path
        self._debug_arg = debug_arg
        assert isinstance(debug_arg, bool)

        self._parse_config_dict()

    def __str__(self):
        props = {k: v for k, v in vars(self).items() if not k.startswith("_")}
        return json.dumps(props, indent=2)

    def _get_cfg(self, keys, default=None, required=False):
        jsonpath = '.'.join(keys)
        try:
            value = reduce(operator.getitem, keys, self._config_dict)
            if value is None or value == "":
                logger.warning(f"'{jsonpath}' is '{value}'")
            return value
        except KeyError:
            if required:
                raise ConfigError(f"required in config: '{jsonpath}'")
            elif default is not None:
                return default
            else:
                return None

    def _parse_config_dict(self):

        # logger first
        self.log = {
            'level': self._get_cfg(["log", "level"], required=True),
            'logfile': self._get_cfg(["log", "logfile"], required=False),
            'json': self._get_cfg(["log", "json"], default=False),
            'stderr': self._get_cfg(["log", "stderrr"], default=True),
            'webhook_access_log': self._get_cfg(
                ["log", "webhook_access_log"], default=None)
        }
        setup_logger(self.log, self._debug_arg)

        self.homeserver = self._get_cfg(
            ["matrix", "homeserver"], required=True)

        self.user_id = self._get_cfg(["matrix", "user_id"], required=True)
        self.passwd = self._get_cfg(["matrix", "passwd"], required=False)
        self.device_name = self._get_cfg(
            ["matrix", "device_name"], required=True)
        self.avatar = self._get_cfg(
            ["matrix", "avatar"], required=False)
        self.rooms = self._get_cfg(
            ["matrix", "rooms"], default=list())

        self.webhook_port = int(self._get_cfg(
            ["webhook", "port"], default=3000))
        self.webhook_host = self._get_cfg(
            ["webhook", "host"], default="127.0.0.1")
        self.webhook_base_url = self._get_cfg(
            ['webhook', 'base_url'], default='/')
        if not self.webhook_base_url.startswith("/"):
            raise ConfigError("webhook.base_url needs to start with '/'")
        if not self.webhook_base_url.endswith("/"):
            self.webhook_base_url = self.webhook_base_url + "/"
        self.webhook_tokens = self._get_cfg(
            ["webhook", "tokens"], default=dict())

        self.notflixbot = self._get_cfg(["notflixbot"], default=dict())
        self.autotrust = self._get_cfg(["autotrust"], default=False)
        self.admin_rooms = self._get_cfg(['admin_rooms'], default=list())
        self.credentials_path = self._get_cfg(["credentials_path"])
        try:
            self.creds = Credentials.read(self.credentials_path)
            logger.debug(f"using stored creds ({self.creds.device_id})")
        except ConfigError:
            self.creds = None
            logger.debug(f"not found: {self.credentials_path}")

        self.storage_path = self._get_cfg(["storage_path"], required=True)

    def update_creds(self, credentials):
        self.creds = Credentials(credentials, self.credentials_path)
        self.creds.write()


class Credentials(Config):

    def _parse_config_dict(self):
        self.user_id = self._get_cfg(["user_id"], required=True)
        self.device_id = self._get_cfg(["device_id"], required=True)
        self.access_token = self._get_cfg(["access_token"], required=True)

    def write(self):
        with open(self._config_path, 'w') as f:
            f.write(json.dumps({
                'user_id': self.user_id,
                'device_id': self.device_id,
                'access_token': self.access_token
            }, indent=2))
        os.chmod(self._config_path, 0o700)
        logger.debug(f"wrote '{self._config_path}'")


def setup_logger(logconf, debug_arg):

    # TODO: switch to using logger.configure

    # removing default logger thats on the stderr sink
    logger.remove()

    loglevel = logconf['level']

    # --debug has precedence, but only affects stderr
    if debug_arg:
        logger.add(
            sys.stderr,
            level="DEBUG",
            enqueue=True,
            filter=lambda r: 'access_log' not in r['extra']
        )
    elif logconf.get('stderr', False) is True:
        logger.add(
            sys.stderr,
            level=loglevel,
            enqueue=True,
            filter=lambda r: 'access_log' not in r['extra']
        )

    if logconf.get('logfile') is not None:
        logger.add(
            logconf['logfile'],
            level=loglevel,
            enqueue=True,
            filter=lambda r: 'access_log' not in r['extra'],
            serialize=logconf['json']
        )

    webhook_access_log = logconf.get('webhook_access_log')
    if webhook_access_log is not None:
        logger.add(
            webhook_access_log,
            level="INFO",
            colorize=True,
            format="<green>{time}</green> | {level} - <level>{message}</level>", # noqa
            enqueue=True,
            filter=lambda r: 'access_log' in r['extra'],
        )
