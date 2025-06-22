import os
from functools import lru_cache
from typing import Optional

from jinja2 import (
    BaseLoader,
    Environment,
    PackageLoader,
    Template,
    nodes,
    select_autoescape,
)
from jinja2.ext import Extension
from jinja2.utils import pass_context

from blacksheep.messages import Request
from blacksheep.server.csrf import AntiForgeryHandler, MissingRequestContextError
from blacksheep.utils import truthy

from .abc import Renderer

_DEFAULT_TEMPLATES_EXTENSION = os.environ.get("APP_JINJA_EXTENSION", ".jinja")


@lru_cache(1200)
def get_template_name(name: str) -> str:
    if not name.endswith(_DEFAULT_TEMPLATES_EXTENSION):
        return name + _DEFAULT_TEMPLATES_EXTENSION
    return name


def render_template(template: Template, *args, **kwargs):
    return template.render(*args, **kwargs)


async def render_template_async(template: Template, *args, **kwargs):
    return await template.render_async(*args, **kwargs)


class AntiForgeryBaseExtension(Extension):
    af_handler: Optional[AntiForgeryHandler] = None

    def __init__(self, environment):
        super().__init__(environment)

        if self.af_handler is None:
            raise TypeError("Define a subclass bound to an AntiForgeryHandler")

    @property
    def handler(self) -> AntiForgeryHandler:
        if self.af_handler is None:
            raise TypeError("Missing anti_forgery_handler")
        return self.af_handler

    def parse(self, parser):
        line_number = next(parser.stream).lineno
        return nodes.CallBlock(self.call_method("get_html"), [], [], "").set_lineno(
            line_number
        )

    def get_token(self, context) -> str:
        try:
            request = context["request"]
        except KeyError:
            raise MissingRequestContextError()
        assert isinstance(request, Request)

        tokens = self.handler.get_tokens(request)
        return tokens[1]


class AntiForgeryInputExtension(AntiForgeryBaseExtension):
    tags = {"csrf_input", "af_input"}

    @pass_context
    def get_html(self, context, caller):
        value = self.get_token(context)
        return (
            f'<input type="hidden" name="{self.handler.form_name}" '
            f'value="{value}" />'
        )


class AntiForgeryValueExtension(AntiForgeryBaseExtension):
    tags = {"csrf_token", "af_token"}

    @pass_context
    def get_html(self, context, caller):
        return self.get_token(context)


class JinjaRenderer(Renderer):
    def __init__(
        self,
        loader: Optional[BaseLoader] = None,
        debug: bool = False,
        enable_async: bool = False,
    ) -> None:
        super().__init__()
        self.env = Environment(
            loader=loader
            or PackageLoader(
                os.environ.get("APP_JINJA_PACKAGE_NAME", "app"),
                os.environ.get("APP_JINJA_PACKAGE_PATH", "views"),
            ),
            autoescape=select_autoescape(["html", "xml", "jinja"]),
            auto_reload=truthy(os.environ.get("APP_JINJA_DEBUG", "")) or debug,
            enable_async=truthy(os.environ.get("APP_JINJA_ENABLE_ASYNC", ""))
            or enable_async,
        )

    def render(self, template: str, model, **kwargs) -> str:
        if model:
            return render_template(
                self.env.get_template(get_template_name(template)), model, **kwargs
            )
        return render_template(
            self.env.get_template(get_template_name(template)), **kwargs
        )

    async def render_async(self, template: str, model, **kwargs) -> str:
        if model:
            return await self.env.get_template(
                get_template_name(template)
            ).render_async(model, **kwargs)
        return await self.env.get_template(get_template_name(template)).render_async(
            **kwargs
        )

    def bind_antiforgery_handler(self, handler) -> None:
        class BoundAntiForgeryInputExtension(AntiForgeryInputExtension):
            af_handler = handler

        class BoundAntiForgeryValueExtension(AntiForgeryValueExtension):
            af_handler = handler

        self.env.add_extension(BoundAntiForgeryInputExtension)
        self.env.add_extension(BoundAntiForgeryValueExtension)
