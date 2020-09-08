import logging
import logging.handlers


logger = None


def get_logger():
    global logger

    if logger is not None:
        return logger

    logger = logging.getLogger("itests")

    logger.setLevel(logging.INFO)

    max_bytes = 24 * 1024 * 1024

    file_handler = logging.handlers.RotatingFileHandler

    handler = file_handler(f"integration_tests.log", maxBytes=max_bytes, backupCount=5)

    handler.setLevel(logging.DEBUG)

    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())

    return logger
