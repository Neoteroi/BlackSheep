import logging


def get_logger():
    """
    Returns a "blacksheep.sessions" logger.
    """
    logger = logging.getLogger("blacksheep.sessions")
    logger.setLevel(logging.INFO)
    return logger
