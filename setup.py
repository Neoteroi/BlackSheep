from setuptools import Extension, setup

COMPILE_ARGS = ["-O2"]
http_parser_dir = "blacksheep/vendor/http-parser"

setup(
    ext_modules=[
        Extension(
            "blacksheep.url",
            ["blacksheep/url.c", f"{http_parser_dir}/http_parser.c"],
            include_dirs=[http_parser_dir],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "blacksheep.exceptions",
            ["blacksheep/exceptions.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "blacksheep.headers",
            ["blacksheep/headers.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "blacksheep.cookies",
            ["blacksheep/cookies.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "blacksheep.contents",
            ["blacksheep/contents.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "blacksheep.messages",
            ["blacksheep/messages.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "blacksheep.scribe",
            ["blacksheep/scribe.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "blacksheep.baseapp",
            ["blacksheep/baseapp.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
    ]
)
