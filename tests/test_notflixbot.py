import configparser

import notflixbot

def test_version():
    # read the version set in pyproject.toml and compare to
    # what the app thinks about itself

    pyproject = configparser.ConfigParser()
    pyproject.read("pyproject.toml")
    pyproject_version = pyproject['tool.poetry']['version'].strip('"')

    assert pyproject_version == notflixbot.__version__
    assert pyproject_version == notflixbot.version_dict['version']

def test_pytest_name():
    assert __name__ == "tests.test_notflixbot"

def test_name():
    assert notflixbot.__name__ == "notflixbot"
