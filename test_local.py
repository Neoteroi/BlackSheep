"""
Test script for async HTTP/2 client against local Docker server.

Before running, setup the test server:
    Linux: bash setup_test_server.sh

Or manually:
docker run --rm -d -p 8443:443 --name http2-server \
-v $(pwd)/nginx-http2.conf:/etc/nginx/nginx.conf:$(whoami) \
-v $(pwd)/certs:/etc/nginx/ssl:$(whoami) \
nginx:alpine

Alternative - Test with public HTTP/2 endpoints:
    python test_public.py
"""

import asyncio
import ssl
import json
from blacksheep import Content
from blacksheep.client.session import ClientSession
from blacksheep.client.pool import ConnectionPool


def disable_ssl_verification(http2=True):
    """
    Create SSL context that doesn't verify certificates.
    Only use for testing with self-signed certificates!

    Args:
        http2: If True, advertise HTTP/2 support via ALPN. If False, only HTTP/1.1.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if http2:
        context.set_alpn_protocols(['h2', 'http/1.1'])
    else:
        # For HTTP/1.1 only, don't advertise HTTP/2
        context.set_alpn_protocols(['http/1.1'])
    return context


def get_detected_protocol(client: ClientSession, host: str, port: int) -> str:
    """
    Get the detected protocol from the connection pool cache.

    Returns:
        The protocol string ('h2' or 'http/1.1') or 'unknown' if not cached.
    """
    for pool in client.pools._pools.values():
        if pool.host == host and pool.port == port:
            key = (host, port)
            if key in pool._protocol_cache:
                return pool._protocol_cache[key]
    return "unknown"


async def test_local_server():
    """Test HTTP/2 client against local Docker server."""
    print("Testing HTTP Client Against Local Server")
    print("=" * 60)

    # For self-signed certificates, disable verification
    ssl_context = disable_ssl_verification()

    # Test 1: Basic request with ClientSession
    print("\n1. Testing ClientSession Basic Request:")
    try:
        async with ClientSession(ssl=ssl_context, http2=True) as client:
            response = await client.get('https://localhost:8443/get')
            protocol = get_detected_protocol(client, 'localhost', 8443)
            body = await response.read() or b""

            print(f"   ✓ Protocol: {protocol}")
            print(f"   ✓ Status: {response.status}")
            print(f"   ✓ Data length: {len(body)} bytes")
            print(f"   ✓ Connection successful")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        print("   Make sure Docker container is running:")
        print("   docker run -d -p 8443:443 --name http2-test-server kennethreitz/httpbin")
        return

    # Test 2: Using ClientSession with various request types
    print("\n2. Testing ClientSession Request Types:")

    try:
        async with ClientSession(ssl=ssl_context, http2=True) as client:
            # GET request
            print("   a) GET request:")
            response = await client.get('https://localhost:8443/get')
            protocol = get_detected_protocol(client, 'localhost', 8443)
            print(f"      ✓ Protocol: {protocol}")
            print(f"      ✓ Status: {response.status}")

            # POST request
            print("   b) POST request:")
            post_data = json.dumps({"test": "data", "timestamp": "2026-01-19"}).encode('utf-8')
            content = Content(b"application/json", post_data)
            response = await client.post('https://localhost:8443/post', content=content)
            protocol = get_detected_protocol(client, 'localhost', 8443)
            print(f"      ✓ Protocol: {protocol}")
            print(f"      ✓ Status: {response.status}")

            # Multiple requests (connection reuse)
            print("   c) Connection reuse test (5 requests):")
            for i in range(5):
                response = await client.get('https://localhost:8443/get')
                protocol = get_detected_protocol(client, 'localhost', 8443)
                print(f"      ✓ Request {i+1}: Status {response.status} (Protocol: {protocol})")

            # Custom headers
            print("   d) Custom headers:")
            custom_headers = {
                'user-agent': 'HTTP2TestClient/1.0',
                'x-custom-header': 'test-value'
            }
            response = await client.get('https://localhost:8443/headers', headers=custom_headers)
            protocol = get_detected_protocol(client, 'localhost', 8443)
            print(f"      ✓ Protocol: {protocol}")
            print(f"      ✓ Status: {response.status}")

            # Delay endpoint (if available)
            print("   e) Testing with delay endpoint:")
            try:
                response = await client.get('https://localhost:8443/delay/2')
                protocol = get_detected_protocol(client, 'localhost', 8443)
                print(f"      ✓ Protocol: {protocol}")
                print(f"      ✓ Status: {response.status}")
            except Exception as e:
                print(f"      ⚠ Delay endpoint not available: {e}")

    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test 3: HTTP/1.1 only mode
    print("\n3. Testing HTTP/1.1 Only Mode:")
    try:
        # Create SSL context without HTTP/2 ALPN
        ssl_context_http1 = disable_ssl_verification(http2=False)
        async with ClientSession(ssl=ssl_context_http1, http2=False) as client:
            response = await client.get('https://localhost:8443/get')
            # When http2=False, the protocol should be http/1.1
            protocol = "http/1.1 (forced)"
            print(f"   ✓ Protocol: {protocol}")
            print(f"   ✓ Status: {response.status}")
    except Exception as e:
        print(f"   ⚠ HTTP/1.1 request failed: {e}")
        print(f"   Note: Check if there's a bug in HTTP/1.1 implementation")

    print("\n" + "=" * 60)
    print("Testing Complete!")
    print("\nTo stop the test server:")
    print("  docker stop http2-test-server && docker rm http2-test-server")


async def test_connection_pool():
    """Test connection pool behavior."""
    print("\n4. Testing Connection Pool:")

    ssl_context = disable_ssl_verification()

    try:
        async with ClientSession(ssl=ssl_context, http2=True) as client:
            print("   Making 10 requests to test pooling:")
            for i in range(10):
                response = await client.get('https://localhost:8443/get')
                protocol = get_detected_protocol(client, 'localhost', 8443)
                print(f"   ✓ Request {i+1}: Status {response.status} (Protocol: {protocol})")

            print("   ✓ Connection pool test complete")

    except Exception as e:
        print(f"   ✗ Error: {e}")


async def test_concurrent_requests():
    """Test true concurrent requests with asyncio.gather."""
    print("\n5. Testing True Concurrent Requests:")

    ssl_context = disable_ssl_verification()

    try:
        async with ClientSession(ssl=ssl_context, http2=True) as client:
            print("   Sending 5 concurrent requests:")
            tasks = [client.get('https://localhost:8443/get') for _ in range(5)]
            responses = await asyncio.gather(*tasks)

            protocol = get_detected_protocol(client, 'localhost', 8443)
            print(f"   Protocol for all requests: {protocol}")
            for i, response in enumerate(responses):
                print(f"   ✓ Concurrent request {i+1}: Status {response.status}")

            print("   ✓ Concurrent requests test complete")

    except Exception as e:
        print(f"   ✗ Error: {e}")


async def test_http2_vs_http1():
    """Compare HTTP/2 and HTTP/1.1 modes."""
    print("\n6. Testing HTTP/2 vs HTTP/1.1 Protocol Detection:")

    ssl_context = disable_ssl_verification()

    try:
        # HTTP/2 enabled
        print("   a) With HTTP/2 enabled:")
        async with ClientSession(ssl=ssl_context, http2=True) as client:
            response = await client.get('https://localhost:8443/get')
            protocol = get_detected_protocol(client, 'localhost', 8443)
            print(f"      ✓ Detected Protocol: {protocol}")
            print(f"      ✓ Status: {response.status}")

        # HTTP/2 disabled
        print("   b) With HTTP/2 disabled:")
        try:
            # Use SSL context without HTTP/2 ALPN
            ssl_context_http1 = disable_ssl_verification(http2=False)
            async with ClientSession(ssl=ssl_context_http1, http2=False) as client:
                response = await client.get('https://localhost:8443/get')
                # http2=False forces HTTP/1.1
                print(f"      ✓ Protocol: http/1.1 (forced by http2=False)")
                print(f"      ✓ Status: {response.status}")
        except Exception as e:
            print(f"      ⚠ HTTP/1.1 failed: {e}")
            print(f"      Note: This may indicate a bug in the HTTP/1.1 connection implementation")

    except Exception as e:
        print(f"   ✗ Error in HTTP/2 test: {e}")


async def main():
    print("\n⚠ WARNING: This test disables SSL certificate verification")
    print("⚠ Only use for testing with local self-signed certificates!\n")

    await test_local_server()
    await test_connection_pool()
    await test_concurrent_requests()
    await test_http2_vs_http1()

    print("\n" + "=" * 60)
    print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
