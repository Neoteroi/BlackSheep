from rodi import GetServiceContext


async def dependency_injection_middleware(request, handler):
    with GetServiceContext() as context:
        request.services_context = context
        return await handler(request)
