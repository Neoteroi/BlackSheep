import uvicorn
from blacksheep import Response, Content, Cookie
from blacksheep.server import Application
from blacksheep.server.responses import text, json
from blacksheep.server.bindings import FromQuery
from itests.utils import CrashTest, ensure_folder


app = Application(show_error_details=True)


app.serve_files('static', discovery=True)


@app.route('/hello-world')
async def hello_world(request):
    return text(f'Hello, World!')


@app.router.head('/echo-headers')
async def echo_headers(request):
    response = Response(200)

    for header in request.headers:
        response.add_header(header[0], header[1])

    return response


@app.route('/echo-cookies')
async def echo_cookies(request):
    cookies = request.cookies
    return json(cookies)


@app.route('/set-cookie')
async def set_cookies(name: FromQuery(str), value: FromQuery(str)):
    response = text('Setting cookie')
    response.set_cookie(Cookie(name.encode(), value.encode()))
    return response


@app.router.post('/echo-posted-json')
async def post_json(request):
    data = await request.json()
    assert data is not None
    return json(data)


@app.router.post('/echo-posted-form')
async def post_form(request):
    data = await request.form()
    assert data is not None
    return json(data)


@app.router.post('/upload-files')
async def upload_files(request):
    files = await request.files()

    assert bool(files)

    folder = 'out'

    ensure_folder(folder)

    for part in files:
        with open(f'./{folder}/{part.file_name.decode()}', mode='wb') as saved_filed:
            saved_filed.write(part.data)

    return json({
        'folder': folder,
        'files': [{'name': file.file_name.decode()} for file in files]
    })


@app.router.get('/echo-query')
async def echo_query(request):
    params = request.query
    return json(params)


@app.router.get('/echo-route/:one/:two/:three')
async def echo_route_values(request):
    params = request.route_values
    return json(params)


@app.router.get('/echo-route-autobind/:one/:two/:three')
async def echo_route_values_autobind(one, two, three):
    return json(dict(one=one, two=two, three=three))


@app.route('/crash')
async def crash(request):
    raise CrashTest()


class Item:

    def __init__(self, name, power):
        self.name = name
        self.power = power


@app.route('/echo-posted-json-autobind', methods=['POST'])
async def upload_item(request, item: Item):
    assert request is not None
    assert item is not None
    return json(item.__dict__)


@app.router.post('/echo-chunked-text')
async def echo_chunked_text(request):
    text_from_client = await request.text()
    return text(text_from_client)


@app.router.post('/echo-streamed-text')
async def echo_streamed_test(request):

    async def echo():
        async for chunk in request.stream():
            yield chunk

    return Response(200, content=Content(b'text/plain; charset=utf-8', echo))


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=44567, log_level="debug")
