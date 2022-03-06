from dataclasses import asdict, is_dataclass
from functools import lru_cache
from typing import Any

from jinja2 import Environment, PackageLoader, Template, select_autoescape
from rodi import Container

from blacksheep import Content, Response


@lru_cache(1200)
def template_name(name: str):
    if not name.endswith(".html"):
        return name + ".html"
    return name


def get_response(html: str):
    return Response(200, [(b"Cache-Control", b"no-cache")]).with_content(
        Content(b"text/html; charset=utf-8", html.encode("utf8"))
    )


def render_template(template: Template, *args, **kwargs):
    return template.render(*args, **kwargs)


async def render_template_async(template: Template, *args, **kwargs):
    return await template.render_async(*args, **kwargs)


def use_templates(app, loader: PackageLoader, enable_async: bool = False):
    env = getattr(app, "jinja_environment", None)
    if not env:
        env = Environment(
            loader=loader,
            autoescape=select_autoescape(["html", "xml"]),
            auto_reload=app.debug,
            enable_async=enable_async,
        )

        app.jinja_environment = env
        app.templates_environment = env

        if isinstance(app.services, Container):

            def get_jinja_env() -> Environment:
                return env

            app.services.add_singleton_by_factory(get_jinja_env)
            app.services.add_alias("jinja_environment", Environment)
            app.services.add_alias("jinja", Environment)
            app.services.add_alias("templates_environment", Environment)
        else:
            raise TypeError(
                "Application services must be an instance of `rodi.Container`."
            )
        env.globals["app"] = app

    if enable_async:

        async def async_view(name: str, model: Any = None, **kwargs):
            return get_response(
                await render_template_async(
                    env.get_template(template_name(name)), model, **kwargs
                )
            )

        return async_view

    def sync_view(name: str, model: Any = None, **kwargs):
        return get_response(
            render_template(env.get_template(template_name(name)), model, **kwargs)
        )

    return sync_view


def model_to_view_params(model):
    if isinstance(model, dict):
        return model
    if is_dataclass(model):
        return asdict(model)
    if hasattr(model, "__dict__"):
        return model.__dict__
    return model


def view(
    jinja_environment: Environment, name: str, model: Any = None, **kwargs
) -> Response:
    """
    Returns a Response object with HTML obtained from synchronous rendering.

    Use this when `enable_async` is set to False when calling `use_templates`.
    """
    if model:
        return get_response(
            render_template(
                jinja_environment.get_template(template_name(name)),
                **model_to_view_params(model),
                **kwargs
            )
        )
    return get_response(
        render_template(jinja_environment.get_template(template_name(name)), **kwargs)
    )


async def view_async(
    jinja_environment: Environment, name: str, model: Any = None, **kwargs
) -> Response:
    """
    Returns a Response object with HTML obtained from synchronous rendering.
    """
    if model:
        return get_response(
            await render_template_async(
                jinja_environment.get_template(template_name(name)),
                **model_to_view_params(model),
                **kwargs
            )
        )
    return get_response(
        await render_template_async(
            jinja_environment.get_template(template_name(name)), **kwargs
        )
    )
