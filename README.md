# `notflixbot`

[![Build Status](https://jenkins.sudo.is/buildStatus/icon?job=ben%2Fnotflixbot%2Fmain&style=flat-square)](https://jenkins.sudo.is/job/ben/job/notflixbot/job/main/)
![Docker Image Version (latest semver)](https://img.shields.io/docker/v/benediktkr/notflixbot?sort=semver&style=flat-square)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/benediktkr/notflixbot?sort=date&style=flat-square)

![](neo.jpeg)

A general purpose matrix bot for [`matrix.sudo.is`](https://matrix.sudo.is),
trying to be extensible.

## Features

 * Matrix bot based on [matrix-nio](https://github.com/poljar/matrix-nio)
 * Unfurls YouTube titles and links to Invidous
 * Add a movie to [Radarr](https://github.com/Radarr/Radarr) from IMDB link with `!add`
 * Webhooks listener. Handles Radarr, Sonarr, Grafana, [Jellyfin](https://github.com/jellyfin/jellyfin-plugin-webhook), Slack and custom webhooks
 * Uses a ZeroMQ `PAIR` socket over `inproc://` transport between webhooks and Matrix client

## Usage

The bot answers to the following commands by default:

 * `!add ${IMDB_URL}`: Add a movie to Radarr
 * `!ruok`: Check if the bot is OK
 * `!whoami`: Show your `user_id`.
 * `!key_sync`: Force a key sync (experimental)
 * `!help`: Show help

## Configuration

Please see [`config-sample.json`](config-sample.json).

To configure where the webhook server listens:

```json
"webhook": {
  "host": "0.0.0.0",
  "port": 3005
  }
```

By default the webhook server listens on `localhost:3000`.

## Running the bot

```shell
usage: notflixbot [-h] [-d] [-c CONFIG] subcmd ...

positional arguments:
  subcmd
    start               Start Matrix bot and webhook HTTP server
    restore_login       Start a new Matrix session
    webhook             Start webhook HTTP server
    Healthcheck         Run healthcheck for webhook HTTP server
    nio                 Low-level stuff, helpful for dev

optional arguments:
  -h, --help            show this help message and exit
  -d, --debug           Enable debug output and logging (default: False)
  -c CONFIG, --config CONFIG
                        Path to config file (default: /etc/notflixbot.json)
```

### Start the bot

The simplest way to start the bot, will use the default configfile `/etc/notflixbot.json`:

```console
$ notflixbot start
notflixbot 0.3.0
Matrix bot user_id: @notflixbot:example.com
Matrix client syncing forever
Polling ZMQ socket for webhook messages
Webhook server listening on: http://127.0.0.1:3033
```

You can use the `-c` flag to specify a path to a different config file:

```shell
notflixbot -c /path/to/a/different/config.json
```

### Docker

You can also use docker (build from `Dockerfile` or use pre-built image):

```shell
mkdir ${PWD}/data
docker run --name notflixbot --rm -v ${PWD}/data:/data -v ${PWD}/config.json:/etc/config.json benediktkr/notflixbot:latest
```

Make sure to configure `credentials_path` and `storage_path` to be
somewhere persisent, for example in `/data` in this example.

### Logging in

Your config has to set `credentials_path` to a path to a file that the
bot can read and write, that will store the credentials (access token,
device id and user id) for the bot.

Log in and create the file with:

```console
$ notflixbot restore_login -c config.json
Password:
```

You can also create the file if you have an access token and device_id
handy:

```json
{
  "user_id": "@notflixbot:exmaple.com",
  "device_id": "ABCDEF1234",
  "acces_token": "abc123
}
```


### `nio` shorthand commands:

```
usage: notflixbot nio [-h] --forget-room FORGET_ROOM

optional arguments:
  -h, --help            show this help message and exit
  --forget-room FORGET_ROOM
                        canonical_alias or room_id
```

## Install libolm depdenency

```shell
apt-get install libolm-dev
```

if this breaks, its because i install -- user pycryptodome

```console
$ python3 -m pip install --user pycryptodome
Collecting pycryptodome
  Downloading pycryptodome-3.18.0-cp35-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 36.9 MB/s eta 0:00:00
Installing collected packages: pycryptodome
ERROR: pip's dependency resolver does not currently take into account all the packages that are installed. This behaviour is the source of the following dependency conflicts.
matrix-nio 0.19.0 requires aiofiles<0.7.0,>=0.6.0, but you have aiofiles 0.8.0 which is incompatible.
matrix-nio 0.19.0 requires aiohttp-socks<0.8.0,>=0.7.0, but you have aiohttp-socks 0.5.3 which is incompatible.
matrix-nio 0.19.0 requires h11<0.13.0,>=0.12.0, but you have h11 0.13.0 which is incompatible.
matrix-nio 0.19.0 requires jsonschema<4.0.0,>=3.2.0, but you have jsonschema 4.17.3 which is incompatible.
matrix-nio 0.19.0 requires unpaddedbase64<3.0.0,>=2.1.0, but you have unpaddedbase64 1.1.0 which is incompatible.
Successfully installed pycryptodome-3.18.0

[notice] A new release of pip available: 22.2.2 -> 23.2
[notice] To update, run: python3 -m pip install --upgrade pip
$ python3 -m pip uninstall --user crypto
```
