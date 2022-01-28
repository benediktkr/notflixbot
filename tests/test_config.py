import json

import pytest

from notflixbot import config, errors

def read_json_file(path):
    with open(path, 'r') as f:
        return json.load(f)

def test_config_file_sample_json():
    conf = read_json_file('config-sample.json')
    assert "matrix" in conf
    assert "webhook" in conf
    assert "log" in conf
    assert "admin_rooms" in conf
    assert "autotrust" in conf
    assert "credentials_path" in conf
    assert "storage_path" in conf
    assert "notflixbot" in conf
    assert len(conf.keys()) == 8

    # matrix section
    assert conf['matrix']['homeserver'] == "https://example.com"
    assert conf['matrix']['user_id'] == "@notflixbot:example.com"
    assert conf['matrix']['rooms'][0] == "#myroom:example.com"
    assert len(conf['matrix']) == 4

    # webhook section
    assert len(conf['webhook']['tokens']) > 0

    # admin_user_ids section
    assert "#admins:example.com" in conf['admin_rooms']

    # log section
    assert conf['log']['level'] in ["DEBUG", "INFO", "WARN", "ERROR"]
    assert conf['log']['stderr'] == True
    assert isinstance(conf['log']['json'], bool)
    assert len(conf['log']) == 5

    assert conf['autotrust'] == False
    assert conf['credentials_path'] == "/data/credentials-sample.json"
    assert conf['storage_path'] == "/data/store"

def test_config_missing_level():
    with pytest.raises(errors.ConfigError):
        config.Config({'stderr': True}, "config-test.json", debug_arg=False)

def test_config_parser():
    conf = config.Config.read('config-sample.json')
    assert conf._config_path == "config-sample.json"
    assert conf.homeserver == "https://example.com"
    assert conf.user_id == "@notflixbot:example.com"
    assert conf.device_name == "sample"
    assert conf.avatar is None
    assert isinstance(conf.rooms, list)
    assert conf.rooms[0] == "#myroom:example.com"
    assert all(a.startswith('#') for a in conf.rooms)
    assert isinstance(conf.webhook_tokens, dict)
    assert len(conf.webhook_tokens.keys()) > 0
    assert conf.webhook_base_url == "/"
    assert conf.webhook_port == 3000
    assert conf.webhook_host == "127.0.0.1"
    assert all(a.startswith('#') for a in conf.admin_rooms)
    assert isinstance(conf.admin_rooms, list)
    assert len(conf.admin_rooms) == 1
    assert "#admins:example.com" in conf.admin_rooms
    assert conf.autotrust is False
    assert conf.credentials_path == "/data/credentials-sample.json"
    assert conf.storage_path == "/data/store"
    assert conf.log['level'] in ["DEBUG", "INFO", "WARN", "ERROR"]
    assert conf.log['logfile'] == "notflixbot.log"
    assert conf.log['json'] is True
    assert conf.log['stderr'] is True
    assert conf.log['webhook_access_log'] == "webhook_access.log"
    assert isinstance(conf.notflixbot, dict)


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
    j['matrix']['avatar'] = "mxc://example.com/foobar"
    conf = config.Config(j, 'config-test.json')
    assert conf.avatar == "mxc://example.com/foobar"

def test_setting_webhook_base_url():
    j = read_json_file("config-sample.json")
    # trailing slash should get added by config.py
    j['webhook']['base_url'] = "/test"
    conf = config.Config(j, 'config-test.json')
    assert conf.webhook_base_url == "/test/"

def test_setting_webhook_base_url_with_trailing_slash():
    j = read_json_file("config-sample.json")
    # just making sure that extra trailing slashes arent added
    j['webhook']['base_url'] = "/test/"
    conf = config.Config(j, 'config-test.json')
    assert conf.webhook_base_url == "/test/"

def test_setting_invalid_webhook_base_url():
    j = read_json_file("config-sample.json")
    j['webhook']['base_url'] = "invalid/"
    with pytest.raises(errors.ConfigError):
        conf = config.Config(j, 'config-test.json')

def test_webhook_base_url_default():
    conf = config.Config.read('config-sample.json')
    assert conf.webhook_base_url == "/"

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

def test_webhook_host_port():
    c = read_json_file('config-sample.json')
    # RFC5737
    c['webhook']['host'] = "128.66.4.20"
    c['webhook']['port'] = "6666"

    conf = config.Config(c, 'config-test.json')
    assert isinstance(conf.webhook_port, int)
    assert conf.webhook_host == "128.66.4.20"
    assert conf.webhook_port == 6666
