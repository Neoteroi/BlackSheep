import os
import uuid
import logging.handlers
from datetime import datetime
from blacksheep.utils.folders import ensure_folder
from .exceptions import InvalidResponseException


def _get_logger():
    process_id = os.getpid()
    
    client_logger = logging.getLogger('blacksheep.client')

    if __debug__:
        client_logger.setLevel(logging.DEBUG)
    else:
        client_logger.setLevel(logging.INFO)

    now = datetime.now()
    ts = now.strftime('%Y%m%d')
    hour_ts = now.strftime('%H%M%S')

    ensure_folder(f'logs/{ts}')

    max_bytes = 24 * 1024 * 1024

    file_handler = logging.handlers.RotatingFileHandler

    client_handler = file_handler(f'logs/{ts}/{hour_ts}-blacksheep-client-{process_id}.log',
                                  maxBytes=max_bytes,
                                  backupCount=5)
    client_handler.setLevel(logging.DEBUG)
    client_handler.setFormatter(logging.Formatter('%(levelname)s %(asctime)s @ BlackSheep.Client: %(message)s'))

    client_logger.addHandler(client_handler)

    return client_logger


def get_logged_url(request):
    if b'?' in request.url.value:
        return request.url.path.decode() + '?<query is hidden>'
    return request.url.path.decode()


def get_response_record(response, trace_id, method, logged_url):
    message = f'({trace_id}) RECEIVED: {str(response.status).ljust(8)} FOR {method.decode()} {logged_url}'
    if response.is_redirect():
        location = response.headers.get_single(b'location')
        if location:
            return message + ' REDIRECT > ' + location.value.decode()
    return message


def get_client_logging_middleware():
    client_logger = _get_logger()

    async def client_logging_middleware(request, handler):
        trace_id = uuid.uuid4()
        logged_url = get_logged_url(request)

        request.trace_id = trace_id
        client_logger.debug(f'({trace_id}) SENDING : {request.method.decode().ljust(8)} {logged_url}')
        try:
            response = await handler(request)
            client_logger.debug(get_response_record(response, trace_id, request.method, logged_url))
        except InvalidResponseException as invalid_response_ex:
            client_logger.warning(f'({trace_id}) SERVER PRODUCED AN INVALID RESPONSE FOR: {request.method.decode()} '
                                f'{get_logged_url(request)} - {invalid_response_ex}')
            raise
        except TimeoutError as timeout:
            client_logger.warning(f'({trace_id}) OPERATION TIMEOUT: {request.method.decode()} '
                                f'{get_logged_url(request)} - {timeout}')
            raise
        except Exception:
            client_logger.exception(f'({trace_id}) UNHANDLED EXCEPTION WHILE HANDLING: {request.method.decode()} '
                                    f'{get_logged_url(request)}')
            raise
        return response

    return client_logging_middleware
