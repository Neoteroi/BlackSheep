from functools import lru_cache
from typing import Any

from blacksheep import Content, Response

from ..settings.html import html


@lru_cache(1200)
def get_template_name(name: str):
    if not name.endswith(".html"):
        return name + ".html"
    return name


def _create_html_response(html: str):
    return Response(200, [(b"Cache-Control", b"no-cache")]).with_content(
        Content(b"text/html; charset=utf-8", html.encode("utf8"))
    )


# TODO: move to `responses`
def view(name: str, model: Any = None, **kwargs) -> Response:
    """
    Returns a Response object with HTML obtained using synchronous rendering.
    """
    name = get_template_name(name)
    renderer = html.renderer
    if model:
        return _create_html_response(
            renderer.render(name, html.model_to_params(model), **kwargs)
        )
    return _create_html_response(renderer.render(name, None, **kwargs))


async def view_async(name: str, model: Any = None, **kwargs) -> Response:
    """
    Returns a Response object with HTML obtained using asynchronous rendering.
    """
    name = get_template_name(name)
    renderer = html.renderer
    if model:
        return _create_html_response(
            await renderer.render_async(name, html.model_to_params(model), **kwargs)
        )
    return _create_html_response(await renderer.render_async(name, None, **kwargs))
