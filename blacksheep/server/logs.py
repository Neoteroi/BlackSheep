import logging
import logging.handlers
from blacksheep.exceptions import HttpException


def get_loggers():
    access_logger = logging.getLogger('server.access')
    app_logger = logging.getLogger('server.app')

    app_logger.setLevel(logging.INFO)
    access_logger.setLevel(logging.DEBUG)

    max_bytes = 24 * 1024 * 1024

    file_handler = logging.handlers.RotatingFileHandler

    access_handler = file_handler('http.log',
                                  maxBytes=max_bytes,
                                  backupCount=5)

    app_handler = file_handler('app.log',
                               maxBytes=max_bytes,
                               backupCount=5)

    access_handler.setLevel(logging.DEBUG)
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(logging.Formatter(
        '%(levelname)s @ %(asctime)s @ %(filename)s '
        '%(funcName)s %(lineno)d: %(message)s'))

    access_logger.addHandler(access_handler)
    app_logger.addHandler(app_handler)

    access_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    return access_logger, app_logger


def get_logged_url(request):
    if b'?' in request.raw_url:
        return (request.url.path.decode() + '?<query is hidden>').ljust(80)
    return request.url.path.decode().ljust(80)


def setup_sync_logging():
    access_logger, app_logger = get_loggers()

    async def logging_middleware(request, handler):
        access_logger.debug(f'{request.method.decode().ljust(8)} {get_logged_url(request)} ({request.client_ip})')
        try:
            response = await handler(request)
        except HttpException:
            raise
        except Exception:
            app_logger.exception(f'{"*" * 30}\nunhandled exception while handling: {request.method.decode()}')
            raise
        return response

    return logging_middleware, access_logger, app_logger

