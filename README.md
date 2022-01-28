# notflixbot

![build status](https://jenkins.sudo.is/buildStatus/icon?job=notflixbot&style=flat-square)
![Docker Image Version (latest semver)](https://img.shields.io/docker/v/benediktkr/notflixbot?sort=semver&style=flat-square)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/benediktkr/notflixbot?sort=date&style=flat-square)

![](neo.jpeg)

a general purpose matrix bot for
[matrix.sudo.is](https://matrix.sudo.is), trying to be extensible.

## features

 * matrix bot based on [matrix-nio](https://github.com/poljar/matrix-nio)
 * show youtube titles and link to invidous
 * add a movie to [radarr](https://github.com/Radarr/Radarr) from imdb link with `!add`
 * webhooks listener. handles radarr, sonarr, grafana, [jellyfin](https://github.com/jellyfin/jellyfin-plugin-webhook), slack and custom webhooks
 * uses a zeromq `PAIR` socket over inproc transport between webhooks and bot

## usage

the bot answers to the following commands by default:

 * `!add`: usage: `!add $IMDB_URL`
 * `!ruok`: check if the bot is ok
 * `!whoami`: show your user id
 * `!key_sync`: force a key sync (experimental)
 * `!help`: show help

## configuration

please see [config-sample.json](config-sample.json).

by default the webhooks will listen on `localhost:3000`, but you can change it by setting

```json
"webhook": {
  "host": "0.0.0.0",
  "port": 3005
  }
```

in the config file

## running the bot

```shell
usage: notflixbot [-h] [-c CONFIG] [-d] subcmd ...

positional arguments:
  subcmd
    start               start matrix bot
    restore_login       start new matrix session
    webhook             start webhook http server
    nio                 low-level stuff, helpful for dev

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        path to config file (default: /etc/config.json)
  -d, --debug           print debug output (default: False)
```


### start the bot

simplest way to start the bot, will use the default configfile `/etc/notflixbot.json`:

```shell
$ notflixbot start
notflixbot 0.1.2
matrix bot running as @notflixbot:example.com
matrix client syncing forever
polling zmq socket
webhook listening on http://127.0.0.1:3033
```

you can use the `-c` flag to specify a path to a different config file:

```shell
notflixbot -c /path/to/a/different/config.json
```

### docker

you can also use docker (build from `Dockerfile` or use pre-built image):

```shell
mkdir ${PWD}/data
docker run --name notflixbot --rm -v ${PWD}/data:/data -v ${PWD}/config.json:/etc/config.json benediktkr/notflixbot:latest
```

make sure to configure `credentials_path` and `storage_path` to be
somewhere persisent, for example in `/data` in this example.

### logging in

your config has to set `credentials_path` to a path to a file that the
bot can read and write, that will store the credentials (access token,
device id and user id) for the bot.

log in and create the file with:

```shell
$ notflixbot restore_login -c config.json
Password:
```


you can also create the file if you have an access token and device_id
handy:

```json
{
  "user_id": "@notflixbot:exmaple.com",
  "device_id": "ABCDEF1234",
  "acces_token": "abc123
}
```


### nio shorthand commands:

```
usage: notflixbot nio [-h] --forget-room FORGET_ROOM

optional arguments:
  -h, --help            show this help message and exit
  --forget-room FORGET_ROOM
                        canonical_alias or room_id
```


## install libolm depdenency

```shell
apt-get install libolm-dev
```
