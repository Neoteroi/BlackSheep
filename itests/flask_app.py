from flask import Flask, Response, escape, jsonify, request

from itests.utils import ensure_folder

# https://flask.palletsprojects.com/en/1.1.x/server/#server
app = Flask(__name__, static_url_path="", static_folder="static")


@app.route("/hello-world")
def hello_world():
    name = request.args.get("name", "World")
    return f"Hello, {escape(name)}!", 200, {"Content-Type": "text/plain"}


@app.route("/echo-headers", methods=["HEAD"])
def echo_headers():
    headers = request.headers
    return "", 200, {name: value for name, value in headers.items()}


@app.route("/close-connection")
def close_connection():
    response = Response("Hello World", 200, mimetype="text/plain")
    response.headers["Connection"] = "close"
    return response


@app.route("/echo-cookies")
def echo_cookies():
    cookies = request.cookies
    return {name: value for name, value in cookies.items()}


@app.route("/set-cookie")
def set_cookies():
    name = request.args.get("name", "Hello")
    value = request.args.get("value", "World")
    response = Response("Hello World", 200, mimetype="text/plain")
    response.set_cookie(name, value)
    return response


@app.route("/echo-posted-json", methods=["POST"])
def post_json():
    data = request.json
    assert data is not None
    return jsonify(data)


@app.route("/echo-posted-form", methods=["POST"])
def post_form():
    data = request.form
    assert data is not None
    return jsonify(data)


# https://flask.palletsprojects.com/en/1.1.x/patterns/fileuploads/
@app.route("/upload-files", methods=["POST"])
def upload_files():
    files = request.files

    assert bool(files)

    folder = "out"

    ensure_folder(folder)

    for part in files.values():
        part.save(f"./{folder}/{part.filename}")

    return jsonify(
        {
            "folder": folder,
            "files": [{"name": file.filename} for file in files.values()],
        }
    )


@app.route("/picture.jpg")
def serve_picture():
    return app.send_static_file("pexels-photo-126407.jpeg")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=44778, debug=True)
