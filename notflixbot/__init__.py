import importlib.metadata
from loguru import logger

__version__ = importlib.metadata.version(__name__)
version_dict = {
    'version': __version__,
    'name': __name__
}
logger.info(f"{__name__} {__version__}")
