import uvicorn
from blacksheep import Response, TextContent
from blacksheep.server import Application
from itests.utils import CrashTest


app_two = Application()


class HandledException(Exception):

    def __init__(self):
        super().__init__('Example exception')


async def handle_test_exception(app, request, http_exception):
    return Response(200, content=TextContent(f'Fake exception, to test handlers'))


app_two.exceptions_handlers[HandledException] = handle_test_exception


@app_two.route('/crash')
async def crash():
    raise CrashTest()


@app_two.route('/handled-crash')
async def crash():
    raise HandledException()


if __name__ == '__main__':
    uvicorn.run(app_two, host='127.0.0.1', port=44566, log_level="debug")
