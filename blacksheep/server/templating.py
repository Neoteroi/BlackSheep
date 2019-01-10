from functools import lru_cache
from blacksheep.server import Application
from blacksheep import Response, Headers, Header, HtmlContent
from jinja2 import Environment, Template, PackageLoader, select_autoescape


@lru_cache(1200)
def template_name(name: str):
    if not name.endswith('.html'):
        return name + '.html'
    return name


def get_response(html: str):
    return Response(200, Headers([
        Header(b'Cache-Control', b'no-cache')
    ]), content=HtmlContent(html))


def render_template(template: Template, model=None):
    if model:
        return template.render(**model)
    return template.render()


def use_templates(app: Application, loader: PackageLoader):
    try:
        env = app.services['jinja_environment']
    except KeyError:
        env = Environment(
            loader=loader,
            autoescape=select_autoescape(['html', 'xml'])
        )

        app.services['jinja_environment'] = env

        env.globals['app'] = app

    def view(name: str, model=None):
        return get_response(render_template(env.get_template(template_name(name)), model))

    return view


def view(request, name: str, model=None):
    return get_response(render_template(request.services.get('jinja_environment').get_template(template_name(name)),
                                        model))
