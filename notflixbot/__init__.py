import importlib.metadata

__version__ = importlib.metadata.version(__name__)
version_dict = {
    'version': __version__,
    'name': __name__
}
