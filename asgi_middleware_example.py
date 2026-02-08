"""
Example: Using ASGI Middleware with BlackSheep

This example demonstrates how to integrate standard ASGI middlewares with BlackSheep
using the ASGIMiddlewareWrapper and use_asgi_middleware helper function.
"""

from blacksheep import Application, get, text
from blacksheep.middlewares import use_asgi_middleware


# Custom ASGI middleware that adds a header to all responses
class CustomHeaderMiddleware:
    def __init__(self, app, header_name: str, header_value: str):
        self.app = app
        self.header_name = header_name.encode()
        self.header_value = header_value.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((self.header_name, self.header_value))
                    message = {**message, "headers": headers}
                await original_send(message)

            await self.app(scope, receive, custom_send)
        else:
            await self.app(scope, receive, send)


# Create BlackSheep application
app = Application()


@get("/")
async def home():
    return text("Hello from BlackSheep with ASGI middleware!")


# Wrap with ASGI middleware
app = use_asgi_middleware(
    app,
    CustomHeaderMiddleware,
    header_name="X-Custom-Server",
    header_value="BlackSheep"
)


# Example: Using with Sentry ASGI Middleware
# Uncomment the following lines if you have sentry-sdk installed:
#
# import sentry_sdk
# from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
#
# sentry_sdk.init(dsn="your-dsn-here")
# app = use_asgi_middleware(app, SentryAsgiMiddleware)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
