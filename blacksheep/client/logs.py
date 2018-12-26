import uuid
import logging.handlers
from .exceptions import InvalidResponseException


client_logger = logging.getLogger('blacksheep.client')

if __debug__:
    client_logger.setLevel(logging.DEBUG)
else:
    client_logger.setLevel(logging.INFO)

max_bytes = 24 * 1024 * 1024

file_handler = logging.handlers.RotatingFileHandler

client_handler = file_handler('blacksheep.client.log',
                              maxBytes=max_bytes,
                              backupCount=5)
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(logging.Formatter('%(levelname)s %(asctime)s @ BlackSheep.Client: %(message)s'))

client_logger.addHandler(client_handler)


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
