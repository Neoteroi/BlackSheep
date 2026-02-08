"""
Example: Using ASGI Middleware with BlackSheep - Both Approaches

This example demonstrates two ways to integrate ASGI middlewares with BlackSheep:
1. Simple wrapper - ASGI middlewares at the application level (beginning)
2. ASGI context preservation - ASGI middlewares anywhere in the chain
"""

from blacksheep import Application, get, text
from blacksheep.middlewares import (
    use_asgi_middleware,
    enable_asgi_context,
    asgi_middleware_adapter,
)


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


# ============================================================================
# APPROACH 1: Simple Wrapper (ASGI middleware at the beginning)
# ============================================================================

def example_approach_1():
    """
    Simple approach: ASGI middleware wraps the entire app.
    
    Best for: Sentry, error tracking, logging at the outermost layer.
    """
    app = Application()
    
    @get("/approach1")
    async def home():
        return text("Hello from Approach 1!")
    
    # Wrap with ASGI middleware at the application level
    app = use_asgi_middleware(
        app,
        CustomHeaderMiddleware,
        header_name="X-Approach",
        header_value="Simple-Wrapper"
    )
    
    return app


# ============================================================================
# APPROACH 2: ASGI Context Preservation (ASGI middleware anywhere)
# ============================================================================

def example_approach_2():
    """
    Enhanced approach: ASGI middlewares can be inserted anywhere.
    
    Best for: Fine-grained control, mixing BlackSheep and ASGI middlewares.
    """
    app = Application()
    
    # Enable ASGI context preservation
    app = enable_asgi_context(app)
    
    # BlackSheep middleware
    async def logging_middleware(request, handler):
        print(f"[BlackSheep MW] Request: {request.method} {request.url.path}")
        response = await handler(request)
        print(f"[BlackSheep MW] Response: {response.status}")
        return response
    
    # Add middlewares in any order!
    app.middlewares.append(logging_middleware)  # BlackSheep middleware first
    app.middlewares.append(
        asgi_middleware_adapter(
            CustomHeaderMiddleware,
            header_name="X-Approach",
            header_value="Context-Preservation"
        )
    )  # ASGI middleware in the middle!
    
    @get("/approach2")
    async def home():
        return text("Hello from Approach 2!")
    
    return app


# ============================================================================
# COMPARISON EXAMPLE: Both approaches in one app
# ============================================================================

def example_comparison():
    """
    Shows both approaches side by side for comparison.
    """
    app = Application()
    
    # Enable context preservation for Approach 2 routes
    app = enable_asgi_context(app)
    
    # BlackSheep middleware
    async def request_logger(request, handler):
        print(f"→ {request.method} {request.url.path}")
        response = await handler(request)
        print(f"← {response.status}")
        return response
    
    app.middlewares.append(request_logger)
    app.middlewares.append(
        asgi_middleware_adapter(
            CustomHeaderMiddleware,
            header_name="X-Mixed",
            header_value="ASGI-In-Chain"
        )
    )
    
    @get("/")
    async def home():
        return text("Choose /approach1 or /approach2")
    
    @get("/approach1")
    async def route1():
        return text("Simple wrapper approach")
    
    @get("/approach2")
    async def route2():
        return text("Context preservation approach")
    
    # Also wrap with outer ASGI middleware (Approach 1)
    app = use_asgi_middleware(
        app,
        CustomHeaderMiddleware,
        header_name="X-Outer",
        header_value="Wrapper"
    )
    
    return app


# ============================================================================
# SENTRY EXAMPLE (Real-world use case)
# ============================================================================

def example_with_sentry():
    """
    Real-world example: Integrating Sentry ASGI middleware.
    
    Uncomment the sentry_sdk imports to use this example.
    """
    app = Application()
    
    @get("/")
    async def home():
        return text("Hello with Sentry!")
    
    @get("/error")
    async def error():
        raise ValueError("Test error for Sentry")
    
    # Approach 1: Simple wrapper (recommended for Sentry)
    # import sentry_sdk
    # from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
    # 
    # sentry_sdk.init(dsn="your-dsn-here")
    # app = use_asgi_middleware(app, SentryAsgiMiddleware)
    
    # Approach 2: ASGI context preservation (if you need more control)
    # app = enable_asgi_context(app)
    # app.middlewares.append(asgi_middleware_adapter(SentryAsgiMiddleware))
    
    return app


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    import uvicorn
    
    # Choose which example to run
    examples = {
        "1": ("Approach 1: Simple Wrapper", example_approach_1),
        "2": ("Approach 2: Context Preservation", example_approach_2),
        "comparison": ("Comparison: Both Approaches", example_comparison),
        "sentry": ("Sentry Integration Example", example_with_sentry),
    }
    
    print("\n" + "="*60)
    print("ASGI Middleware Integration Examples")
    print("="*60)
    for key, (description, _) in examples.items():
        print(f"  {key}: {description}")
    print("="*60 + "\n")
    
    if len(sys.argv) > 1 and sys.argv[1] in examples:
        choice = sys.argv[1]
    else:
        choice = "comparison"  # Default
    
    description, example_fn = examples[choice]
    app = example_fn()
    
    print(f"Running: {description}")
    print("Server starting at http://127.0.0.1:8000")
    print("\nPress Ctrl+C to stop\n")
    
    uvicorn.run(app, host="127.0.0.1", port=8000)
