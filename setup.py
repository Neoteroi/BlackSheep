from setuptools import setup, Extension


def readme():
    with open("README.md") as f:
        return f.read()


COMPILE_ARGS = ["-O2"]


setup(
    name="neoteroi-web",
    version="2.0.0",
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
    keywords="Neoteroi web framework",
    platforms=["*nix"],
    license="MIT",
    packages=[
        "neoteroi.web",
        "neoteroi.web.server",
        "neoteroi.web.server.authentication",
        "neoteroi.web.server.authorization",
        "neoteroi.web.server.files",
        "neoteroi.web.server.remotes",
        "neoteroi.web.server.res",
        "neoteroi.web.server.openapi",
        "neoteroi.web.server.security",
        "neoteroi.web.settings",
        "neoteroi.web.client",
        "neoteroi.web.common",
        "neoteroi.web.common.files",
        "neoteroi.web.sessions",
        "neoteroi.web.testing",
        "neoteroi.web.utils",
    ],
    ext_modules=[
        Extension(
            "neoteroi.web.url",
            ["neoteroi/web/url.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "neoteroi.web.exceptions",
            ["neoteroi/web/exceptions.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "neoteroi.web.headers",
            ["neoteroi/web/headers.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "neoteroi.web.cookies",
            ["neoteroi/web/cookies.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "neoteroi.web.contents",
            ["neoteroi/web/contents.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "neoteroi.web.messages",
            ["neoteroi/web/messages.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "neoteroi.web.scribe",
            ["neoteroi/web/scribe.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
        Extension(
            "neoteroi.web.baseapp",
            ["neoteroi/web/baseapp.c"],
            extra_compile_args=COMPILE_ARGS,
        ),
    ],
    install_requires=[
        "httptools>=0.5",
        "certifi>=2022.9.24",
        "cchardet~=2.1.7; python_version < '3.11'",
        "chardet==5.0.0; python_version > '3.10'",
        "neoteroi-auth==0.0.3",  # ~=1.0.0
        "neoteroi-di==0.0.4",  # ~=2.0.0
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
        ],
        "jinja": [
            "Jinja2~=3.1.2",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
