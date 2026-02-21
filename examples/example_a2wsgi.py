"""
Example: Using BlackSheep with a2wsgi

This example demonstrates how to use BlackSheep (an ASGI framework) with
a2wsgi to run on WSGI servers like Gunicorn with sync workers, uWSGI, or
mod_wsgi.

Installation:
    pip install blacksheep a2wsgi gunicorn

Usage:
    # Run with Gunicorn (WSGI server)
    gunicorn example_a2wsgi:wsgi_app -w 4

    # Or with uWSGI
    uwsgi --http :8000 --wsgi-file example_a2wsgi.py --callable wsgi_app
"""
from pathlib import Path
from blacksheep import Application, text, json, html
from a2wsgi import ASGIMiddleware


# Create BlackSheep application
app = Application()


# Configure static file serving (now a2wsgi compatible!)
# This will serve files with Content-Length headers instead of chunked encoding
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.serve_files(static_path, root_path="/static")


# Define some routes
@app.router.get("/")
async def home():
    return html("""
        <html>
            <head>
                <title>BlackSheep + a2wsgi</title>
            </head>
            <body>
                <h1>BlackSheep with a2wsgi</h1>
                <p>This BlackSheep application is running through a2wsgi!</p>
                <ul>
                    <li><a href="/api/info">API Info</a></li>
                    <li><a href="/api/health">Health Check</a></li>
                </ul>
            </body>
        </html>
    """)


@app.router.get("/api/info")
async def api_info():
    """API endpoint returning JSON."""
    return json({
        "framework": "BlackSheep",
        "adapter": "a2wsgi",
        "description": "ASGI to WSGI bridge",
        "features": [
            "Static file serving with Content-Length",
            "Full BlackSheep functionality",
            "Compatible with WSGI servers"
        ]
    })


@app.router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return json({"status": "healthy", "message": "All systems operational"})


@app.router.post("/api/echo")
async def echo(data: dict):
    """Echo back the received JSON data."""
    return json({"received": data, "echo": True})


# Important: Start the application
@app.on_start
async def on_start(application: Application):
    """Application startup handler."""
    print("BlackSheep application started!")
    print("Available routes:")
    for route in application.router:
        print(f"  {route.pattern.decode() if isinstance(route.pattern, bytes) else route.pattern}")


# Wrap the ASGI app with a2wsgi to create a WSGI app
# This is the WSGI callable that WSGI servers expect
wsgi_app = ASGIMiddleware(app)


if __name__ == "__main__":
    # For development, you can still use uvicorn (ASGI server)
    print("For development with ASGI:")
    print("  uvicorn example_a2wsgi:app --reload")
    print()
    print("For production with WSGI:")
    print("  gunicorn example_a2wsgi:wsgi_app -w 4")
    print("  uwsgi --http :8000 --wsgi-file example_a2wsgi.py --callable wsgi_app")

    # Or run with uvicorn if available
    try:
        import uvicorn
        print("\nStarting with uvicorn (ASGI)...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except ImportError:
        print("\nInstall uvicorn to run directly: pip install uvicorn")
