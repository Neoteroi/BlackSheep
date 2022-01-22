import blacksheep
import pathlib

from blacksheep.server.responses import redirect
from blacksheep.server.websocket import WebSocket

STATIC_PATH = pathlib.Path(__file__).parent / 'static'

app = blacksheep.Application()
app.serve_files(STATIC_PATH, root_path='/static')


@app.router.ws('/ws/{client_id}')
async def ws(websocket: WebSocket, client_id: str):
    await websocket.accept()
    print(f'{client_id=}')

    while True:
        msg = await websocket.receive_text()
        await websocket.send_text(msg)


@app.router.get('/')
def r():
    return redirect('/static/chat.html')
