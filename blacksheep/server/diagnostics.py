from blacksheep import Application, Router, html
from blacksheep.server.errors import ServerErrorDetailsHandler


def _get_response_without_details(request, info, error_page_template: str):
    content = error_page_template.format_map(
        {
            "info": info,
            "exctype": "",
            "excmessage": "",
            "method": request.method,
            "path": request.url.value.decode(),
            "full_url": "",
        }
    )

    return html(content, status=503)


def get_diagnostic_app(exc: Exception, match: str = "/*") -> Application:
    """
    Returns a fallback application, to help diagnosing start-up errors.

    Example:

        def get_app():
            try:
                # ... your code that configures the application object
                return configure_application()
            except Exception as exc:
                return get_diagnostic_app(exc)


        app = get_app()
    """
    router = Router()
    error_details_handler = ServerErrorDetailsHandler()

    app = Application(router=router)

    @router.get(match)
    async def diagnostic_home(request):
        if app.show_error_details:
            response = error_details_handler.produce_response(request, exc)
            response.status = 503
            return response
        return _get_response_without_details(
            request,
            (
                "The application failed to start. Error details are hidden for security"
                " reasons. To display temporarily error details and investigate the "
                "issue, configure temporarily the environment to display error details."
                "APP_SHOW_ERROR_DETAILS=1"
            ),
            error_details_handler._error_page_template,
        )

    return app
