from flask import Flask, jsonify, redirect, request
from flask.wrappers import Response
from markupsafe import escape

from itests.utils import ensure_folder

# https://flask.palletsprojects.com/en/1.1.x/server/#server
app = Flask(__name__, static_url_path="", static_folder="static")


@app.route("/hello-world")
def hello_world():
    name = request.args.get("name", "World")
    return f"Hello, {escape(name)}!", 200, {"Content-Type": "text/plain"}


@app.route("/plain-json")
async def plain_json():
    return jsonify({"message": "Hello, World!"})


@app.route("/plain-json-error-simulation")
async def plain_json_error_simulation():
    response = jsonify({"message": "Hello, World!"})
    response.status_code = 500
    return response


@app.route("/echo-headers", methods=["HEAD"])
def echo_headers():
    headers = request.headers
    return "", 200, {name: value for name, value in headers.items()}


@app.route("/close-connection")
def close_connection():
    response = Response("Hello World", 200, mimetype="text/plain")
    response.headers["Connection"] = "close"
    return response


@app.route("/redirect-setting-cookie")
def redirect_setting_cookie():
    response = redirect("/redirect-requiring-cookie")
    response.set_cookie("x-key", "example")
    return response


@app.route("/redirect-requiring-cookie")
def redirect_requiring_cookie():
    cookies = request.cookies
    if cookies.get("x-key") == "example":
        response = Response("Hello World", 200, mimetype="text/plain")
    else:
        response = Response("Unauthorized", 401, mimetype="text/plain")
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


@app.route("/upload-raw/<filename>", methods=["POST"])
def upload_raw_file(filename):
    """Accept a raw file upload (not multipart)."""
    folder = "out"
    ensure_folder(folder)

    file_path = f"./{folder}/{filename}"
    with open(file_path, "wb") as f:
        f.write(request.data)

    return jsonify(
        {
            "folder": folder,
            "filename": filename,
            "size": len(request.data),
        }
    )


@app.route("/picture.jpg")
def serve_picture():
    return app.send_static_file("pexels-photo-126407.jpeg")


# region for OIDC test


@app.route("/oidc/.well-known/openid-configuration")
def get_well_known_oidc_configuration():
    return jsonify(
        {
            "issuer": "https://neoteroi.dev/",
            "authorization_endpoint": "https://neoteroi.dev/authorization",
            "token_endpoint": "https://neoteroi.dev/token",
            "jwks_uri": "http://127.0.0.1:44777/oidc/.well-known/jwks.json",
            "end_session_endpoint": "https://neoteroi.dev/sign-out",
        }
    )


@app.route("/oidc/.well-known/jwks.json")
def get_well_known_jwks_configuration():
    return jsonify(
        {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "0",
                    "n": "xzO7x0gEMbktuu5RLUqiABJNqt4kdm_5ucsKgSdHUdUcbkG28dLAikoFTki9awmyapSbO84zlKMaH24obOe44hd32sdeMOdQp0TxpxE95HfYVFuAWdfCM4Bz_x32Sq51e7x6oZd09vODFFbwTlMJ27LPAEuI5G6UVQKxhIB_wA2FOPkbHeDncB7jYv9kLidvpNgp5PC-aKHKv9ay6gi7M-wUQEpeQMjpyDFN2p_q12BWSUbsRwOjhYtCuSmmBNh07MizzVIQjpmZU5f6qmZHw--iJSBD52wsI87itYbBwRcDN5ffColkFpA8va0hDlShI2qVmwtQ3LUpZVivKuJOSw==",
                    "e": "AQAB",
                },
                {
                    "kty": "RSA",
                    "kid": "1",
                    "n": "3a-KHqLSxXba1e-qa2cWaV6VNd3LsNptZsbd1eZj402lehEbHm8ZdjHlZNwirPeqhvHYbCGRKfqLV2jE1UacfkCmcP8u7klENFbl01IyA8-MiVfmRB6BWlaBNS0NCDIGJ1GY7aPfEOJgGc5L4laIAD6iSVTfUwNtkLVAHXx5OQjJIVIxk6Vkji1n2JvpEO9337Kp96-AqfpIFWyCLg56uGJfK6XdlDYZvPm17xorcLGUB9MBsOID7PbdqeVnmaKW9aFNZj1OaDTZAsNqnxGkmsp3wkds8Th3raIbYvotQEGm1BCdEbqj3hu05bIEZuQbWuNTIseYCKFw7GJXawEKzQ==",
                    "e": "AQAB",
                },
                {
                    "kty": "RSA",
                    "kid": "2",
                    "n": "nk4LTnUzUBqmQTdMmNaHRU6FHHHXfW7TwOoVnCSu36PKyFovRGs5Qiec1VBmF4PZCXlkAwmpBPf4iBbWr3xXU4lE8d3OBuqnf-qFWbOCkyNFp_kyqHu7SlGHJhYilfRzKqDGJ5FqIafBpXID_FsxTqNi-mf98G_jm_QoF5ifMAPUf0eVTCjzs9fcawnKDbeaAED3SbYJt-EVjdcOJalilXJWPNdpGx8ouF1Zn77NDEbj6_1BBk22AZI1yQzDy8c08HlEK1NQgToJyQ-CLP6deHYiHrxMSZe83WbkCvxr1PLMFZlUTWh2AcgbiR9zJARu7nk6PWTbBhreuXRL5meGMQ==",
                    "e": "AQAB",
                },
                {
                    "kty": "RSA",
                    "kid": "3",
                    "n": "v_6KlxHChgEdhvV5t6cDi2h-u2y355dxkwIp1YM4YINXKNStSnFUTkRIPXAY9H15kn6CuWCSWXl7jRwCPm5UOBnC9TjKJTuTK_IVJrTqd1dFkxOEsesKKBPsc0nBjtYMc0c_74K0OxJphy6I4d0M6gXWVOx1avOMEU7LQHE18WtfSYXtBk_Q51foM8StqFARCKAdyRZRXwhtS71lPrHNLhU2aayKBKpWL-r-q4KZGwDLtw0z3bHR5Z_bIJVGushkYLN_DaJvkvypb1y7Lq6ozMovLA5xHgYhv6VCUGWOAJWo9PZXjtwjrO8gXME-msBmB7iO-ltV0FM3O9wTqsJJxw==",
                    "e": "AQAB",
                },
                {
                    "kty": "RSA",
                    "kid": "4",
                    "n": "xavcr0IyifTHONNFnCg8-DveYcH1Pl8geSAIXaMtRs76Hdz-swE-x8kRCqJ0KWLUkP5tgWVRhp0ErkMWEeZ18fRNnXcdU6BVoMLvLLME3OQPJiJpd3Xu7jdYL1fCL1tsO1-zTQUSRc0xoFpg4C_U8ojxGMjFJwHjCYZ41Vm-imDEbfyHRUc5PHtbsfm4_aM9JLyC8cHhNwPpnMZDBXAp9aV8b1N4PZhQmAF_9as2Q5j1DTOcROBBDHGARv6StFO9VYC5JMvVBdWuOd85KLP7CZuu24Cs8bEiHxX95wKIBaWAjQ4sOaXhhWllS-SFsF8K4VyuveJCTIs4FyzDKESy7Q==",
                    "e": "AQAB",
                },
            ]
        }
    )


# endregion


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=44777, debug=True)
