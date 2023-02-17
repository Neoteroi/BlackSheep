from setuptools import setup, Extension


def readme():
    with open("README.md") as f:
        return f.read()


COMPILE_ARGS = ["-O2"]


setup(
    name="blacksheep",
    version="1.2.10",
    description="Fast web framework for Python asyncio",
    long_description=readme(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Environment :: Web Environment",
        "Operating System :: OS Independent",
        "Framework :: AsyncIO",
    ],
    setup_requires=["wheel"],
    url="https://github.com/Neoteroi/BlackSheep",
    author="Roberto Prevato",
    author_email="roberto.prevato@gmail.com",
    keywords="BlackSheep web framework",
    platforms=["*nix"],
    license="MIT",
    packages=[
        "blacksheep",
        "blacksheep.plugins",
        "blacksheep.server",
        "blacksheep.server.authentication",
        "blacksheep.server.authorization",
        "blacksheep.server.files",
        "blacksheep.server.remotes",
        "blacksheep.server.res",
        "blacksheep.server.openapi",
        "blacksheep.server.security",
        "blacksheep.client",
        "blacksheep.common",
        "blacksheep.common.files",
        "blacksheep.sessions",
        "blacksheep.testing",
        "blacksheep.utils",
    ],
    ext_modules=[
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
    ],
    install_requires=[
        "httptools>=0.5",
        "Jinja2~=3.1.2",
        "certifi>=2022.9.24",
        "cchardet~=2.1.7; python_version < '3.11'",
        "chardet==5.0.0; python_version > '3.10'",
        "guardpost~=0.0.9",
        "rodi~=1.1.1",
        "essentials>=1.1.4,<2.0",
        "essentials-openapi>=0.1.4,<1.0",
        "typing_extensions; python_version < '3.8'",
        "python-dateutil~=2.8.2",
        "itsdangerous~=2.1.2",
    ],
    extras_require={
        "full": [
            "cryptography~=38.0.1",
            "PyJWT~=2.6.0",
            "websockets~=10.3",
        ]
    },
    include_package_data=True,
    zip_safe=False,
)
