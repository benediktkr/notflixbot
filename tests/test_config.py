import json

import pytest

from notflixbot import config, errors

def read_json_file(path):
    with open(path, 'r') as f:
        return json.load(f)

def test_config_file_sample_json():
    conf = read_json_file('config-sample.json')
    assert "matrix" in conf
    assert "log" in conf
    assert "cmd_prefixes" in conf
    assert "autotrust" in conf
    assert "credentials_path" in conf
    assert "storage_path" in conf
    assert len(conf.keys()) == 6

    # matrix section
    assert conf['matrix']['homeserver'] == "https://matrix.org"
    assert conf['matrix']['user_id'] == "@notflixbot:matrix.org"
    assert len(conf['matrix']) == 3

    # log section
    assert conf['log']['level'] in ["DEBUG", "INFO", "WARN", "ERROR"]
    assert conf['log']['stderr'] == True
    assert isinstance(conf['log']['json'], bool)
    assert len(conf['log']) == 4

    assert conf['cmd_prefixes']["!c"] == "cmd"
    assert len(conf['cmd_prefixes']) == 1
    assert conf['autotrust'] == False
    assert conf['credentials_path'] == "credentials-sample.json"
    assert conf['storage_path'] == "/var/lib/notflixbot/store"

def test_config_missing_level():
    with pytest.raises(errors.ConfigError):
        config.Config({'stderr': True}, "config-test.json", debug_arg=False)

def test_config_parser():
    conf = config.Config.read('config-sample.json')
    assert conf._config_path == "config-sample.json"
    assert conf.homeserver == "https://matrix.org"
    assert conf.user_id == "@notflixbot:matrix.org"
    assert conf.device_name == "sample"
    assert conf.avatar is None
    assert conf.cmd_prefixes["!c"] == "cmd"
    assert len(conf.cmd_prefixes) == 1
    assert conf.autotrust is False
    assert conf.credentials_path == "credentials-sample.json"
    assert conf.storage_path == "/var/lib/notflixbot/store"
    assert conf.log['level'] in ["DEBUG", "INFO", "WARN", "ERROR"]
    assert conf.log['logfile'] == "notflixbot.log"
    assert conf.log['json'] is True
    assert conf.log['stderr'] is True


def test_config_parser_homeserver():
    conf = config.Config.read('config-sample.json')
    conf_d = read_json_file("config-sample.json")
    assert conf_d['matrix']['homeserver'] == conf.homeserver

def test_config_parser_empty():
    with pytest.raises(errors.ConfigError):
        config.Config(dict(), "config-test.json")

def test_config_parser_missing_homeserver():
    c = read_json_file("config-sample.json")
    del c['matrix']['homeserver']
    with pytest.raises(errors.ConfigError):
        config.Config(c, "config-sample.json")

def test_config_parser_missing_matrix_section():
    c = read_json_file("config-sample.json")
    del c['matrix']
    with pytest.raises(errors.ConfigError):
        config.Config(c, "config-sample.json")

def test_config_parser_missing_non_required():
    j = read_json_file("config-sample.json")
    del j['log']['logfile']
    del j['log']['json']
    del j['log']['stderr']
    conf = config.Config(j, "config-test.json")
    assert conf.homeserver == j['matrix']['homeserver']

def test_avatar():
    j = read_json_file("config-sample.json")
    # not real mxc uri
    j['matrix']['avatar'] = "mxc://matrix.org/foobar"
    conf = config.Config(j, 'config-test.json')
    assert conf.avatar == "mxc://matrix.org/foobar"

def test_config_parser_missing_wihout_default():
    j = read_json_file("config-sample.json")
    del j['log']['json']
    conf = config.Config(j, "config-test.json")
    assert conf.log['json'] is False

def test_config_parser_missing_with_default():
    j = read_json_file("config-sample.json")
    del j['log']['stderr']
    conf = config.Config(j, "config-test.json")
    assert conf.log['stderr'] is True

def test_credentials_not_avail():
    conf = config.Config.read('config-sample.json')
    assert conf.creds is None

def test_passwd():
    j = read_json_file("config-sample.json")
    j['matrix']['passwd'] = "hunter4"
    c = config.Config(j, "config-test.json")
    assert c.passwd == "hunter4"

def test_creds():
    def write_noop(foo):
        pass

    config.Credentials.write = write_noop

    conf = config.Config.read('config-sample.json')
    conf.update_creds({'user_id': conf.user_id, 'device_id': 'UNIT__TEST', 'access_token': 'nah'})

    assert conf.creds.device_id == "UNIT__TEST"
    assert len(conf.creds.device_id) == 10
    assert conf.creds.user_id == conf.user_id
    assert conf.creds.access_token is not None

def test_autotrust_default():
    c = read_json_file('config-sample.json')
    del c['autotrust']
    assert 'autotrust' not in c
    conf = config.Config(c, 'config-test.json')
    assert conf.autotrust is False
