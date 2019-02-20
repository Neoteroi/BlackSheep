import os
import logging
import logging.handlers
from datetime import datetime
from blacksheep.utils.folders import ensure_folder
from blacksheep.exceptions import HttpException, MessageAborted


def _get_loggers():
    process_id = os.getpid()

    access_logger = logging.getLogger('blacksheep.server-access')
    app_logger = logging.getLogger('blacksheep.server')

    app_logger.setLevel(logging.INFO)
    access_logger.setLevel(logging.DEBUG)

    max_bytes = 24 * 1024 * 1024

    file_handler = logging.handlers.RotatingFileHandler

    now = datetime.now()
    ts = now.strftime('%Y%m%d')
    hour_ts = now.strftime('%H%M%S')

    ensure_folder(f'logs/{ts}')

    access_handler = file_handler(f'logs/{ts}/{hour_ts}-blacksheep-access-{process_id}.log',
                                  maxBytes=max_bytes,
                                  backupCount=5)

    app_handler = file_handler(f'logs/{ts}/{hour_ts}-blacksheep-{process_id}.log',
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
    if request.url.query:
        return request.url.path.decode() + '?<query is hidden>'
    return request.url.path.decode()


def setup_sync_logging():
    access_logger, app_logger = _get_loggers()

    async def logging_middleware(request, handler):
        access_logger.debug(f'{request.method.decode().ljust(8)} {get_logged_url(request)}')
        try:
            response = await handler(request)
        except HttpException:
            raise
        except MessageAborted:
            app_logger.warning(f'The connection was lost or aborted while the request was being sent. '
                               f'{request.method.decode().ljust(8)} {get_logged_url(request)}')
            raise
        except Exception:
            app_logger.exception(f'{"*" * 30}\nunhandled exception while handling: {request.method.decode()} {get_logged_url(request)}')
            raise
        return response

    return logging_middleware, access_logger, app_logger

