from flask import Flask, escape, request, Response, jsonify


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


@app.route('/echo-posted-json', methods=['POST'])
def post_json():
    data = request.json
    assert data is not None
    return jsonify(data)


@app.route('/echo-posted-form', methods=['POST'])
def post_form():
    data = request.form
    assert data is not None
    return jsonify(data)


# https://flask.palletsprojects.com/en/1.1.x/patterns/fileuploads/
@app.route('/', methods=['POST'])
def upload_file():
    file = request.files['file']

    # TODO
    return 'TODO'