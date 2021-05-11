from setuptools import setup, Extension


def readme():
    with open("README.md") as f:
        return f.read()


COMPILE_ARGS = ["-O2"]


setup(
    name="blacksheep",
    version="1.0.5",
    description="Fast web framework and HTTP client for Python asyncio",
    long_description=readme(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
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
        "blacksheep.server",
        "blacksheep.server.files",
        "blacksheep.server.res",
        "blacksheep.client",
        "blacksheep.common",
        "blacksheep.common.files",
        "blacksheep.sessions",
    ],
    ext_modules=[
        Extension(
            "blacksheep.url", ["blacksheep/url.c"], extra_compile_args=COMPILE_ARGS
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
        "httptools==0.2.*",
        "Jinja2==2.11.3",
        "certifi>=2020.12.5",
        "cchardet~=2.1.5",
        "guardpost~=0.0.7",
        "rodi~=1.1.1",
        "essentials==1.1.4",
        "essentials-openapi==0.1.2",
        "typing_extensions; python_version < '3.8'",
        "python-dateutil==2.8.1",
        "itsdangerous==1.1.0",
    ],
    extras_require={
        "full": [
            "cryptography==3.4.6",
        ]
    },
    include_package_data=True,
    zip_safe=False,
)
