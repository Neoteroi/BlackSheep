"""
This file is used to specify Python extensions, which are used when using Cython.
Extensions are used only if the current runtime is CPython and only if there is not an
environment variable: `BLACKSHEEP_NO_EXTENSIONS=1`.
The logic is to support PyPy. See:
https://github.com/Neoteroi/BlackSheep/issues/539#issuecomment-2888631226
"""

import os
from setuptools import Extension, setup
import platform

COMPILE_ARGS = ["-O2"]

# Check for environment variable to skip extensions
skip_ext = os.environ.get("BLACKSHEEP_NO_EXTENSIONS", "0") == "1"


if platform.python_implementation() == "CPython" and not skip_ext:
    ext_modules = [
        Extension(
            "blacksheep.url",
            ["blacksheep/url.c"],
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
else:
    ext_modules = []

setup(ext_modules=ext_modules)
