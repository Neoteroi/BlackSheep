from flask import Flask, escape, request, Response


# https://flask.palletsprojects.com/en/1.1.x/server/#server
app = Flask(__name__)


@app.route('/hello-world')
def hello_world():
    name = request.args.get('name', 'World')
    return f'Hello, {escape(name)}!', 200, {'Content-Type': 'text/plain'}


@app.route('/echo-headers', methods=['HEAD'])
def echo_headers():
    headers = request.headers
    return '', 200, {name: value for name, value in headers.items()}


@app.route('/echo-cookies')
def echo_cookies():
    cookies = request.cookies
    return {name: value for name, value in cookies.items()}


@app.route('/set-cookie')
def set_cookies():
    name = request.args.get('name', 'Hello')
    value = request.args.get('value', 'World')
    response = Response('Hello World', 200, mimetype='text/plain')
    response.set_cookie(name, value)
    return response

