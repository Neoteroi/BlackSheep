"""
Test async HTTP/2 client against public HTTP/2 servers.
This validates the client works without needing Docker.
"""

import asyncio
from blacksheep.client.session import ClientSession
from blacksheep.client.connection import HTTP2Connection


async def test_public_servers():
    """Test against well-known public HTTP/2 servers."""
    print("Testing HTTP/2 Client Against Public Servers")
    print("=" * 60)

    async with ClientSession() as session:
        # Test 1: Google (known HTTP/2 support)
        print("\n1. Testing with Google:")
        try:
            response = await session.get('https://www.google.com/')
            print(f"   ✓ Status: {response.status}")
            print(f"   ✓ Data length: {len(await response.read())} bytes")
            print(f"   ✓ Response received successfully")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # Test 2: Cloudflare (known HTTP/2 support)
        print("\n2. Testing with Cloudflare:")
        try:
            response = await session.get('https://cloudflare.com/')
            print(f"   ✓ Status: {response.status}")
            print(f"   ✓ Data length: {len(await response.read())} bytes")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # Test 4: GitHub API (HTTP/2)
        print("\n4. Testing with GitHub API:")
        try:
            response = await session.get('https://api.github.com/')
            data = await response.read()
            print(f"   ✓ Status: {response.status}")
            print(f"   ✓ Response: {data[:100].decode('utf-8', errors='ignore')}...")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # Test 5: Multiple requests (connection reuse)
        print("\n5. Testing Connection Reuse (5 requests to Google):")
        try:
            for i in range(5):
                response = await session.get('https://www.google.com/')
                print(f"   ✓ Request {i+1}: Status {response.status}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # Test 6: Custom headers
        print("\n6. Testing with Custom Headers:")
        try:
            headers = {
                'user-agent': 'BlackSheep-HTTP2Client/1.0 TestScript',
                'accept': 'text/html'
            }
            response = await session.get('https://www.google.com/', headers=headers)
            print(f"   ✓ Status: {response.status}")
            print(f"   ✓ Custom headers sent successfully")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # Test 7: Concurrent requests
        print("\n7. Testing Concurrent Requests (5 parallel to Google):")
        try:
            tasks = [session.get('https://www.google.com/') for _ in range(5)]
            responses = await asyncio.gather(*tasks)
            for i, response in enumerate(responses):
                print(f"   ✓ Concurrent request {i+1}: Status {response.status}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

    print("\n" + "=" * 60)
    print("Public server tests completed!")


async def verify_http2_protocol():
    """Verify that HTTP/2 is actually being used."""
    print("\n\nVerifying HTTP/2 Protocol Usage")
    print("=" * 60)

    try:
        from blacksheep.client.pool import ConnectionPool

        # Create a pool with HTTP/2 enabled
        pool = ConnectionPool(
            scheme=b"https",
            host=b"www.google.com",
            port=443,
            ssl=None,
            http2=True
        )

        # Get a connection - should auto-detect HTTP/2
        conn = await pool.get_connection()

        if isinstance(conn, HTTP2Connection):
            print("✓ HTTP/2 connection detected!")
            print(f"✓ Connection type: {type(conn).__name__}")

            # Check negotiated protocol if available
            if hasattr(conn, 'writer') and conn.writer:
                ssl_object = conn.writer.get_extra_info('ssl_object')
                if ssl_object:
                    negotiated = ssl_object.selected_alpn_protocol()
                    print(f"✓ Negotiated protocol: {negotiated}")
        else:
            print(f"⚠ Connection type: {type(conn).__name__}")
            print("  (HTTP/1.1 may be used if server doesn't support HTTP/2)")

        # Clean up
        pool.dispose()
        print("✓ Protocol verification completed")

    except Exception as e:
        print(f"✗ Error during protocol verification: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)


async def main():
    await test_public_servers()
    await verify_http2_protocol()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("\nNote: BlackSheep HTTP client now supports HTTP/2!")
    print("HTTP/2 is enabled by default with automatic fallback to HTTP/1.1")
    print("To disable HTTP/2: ClientSession(http2=False)")


if __name__ == "__main__":
    asyncio.run(main())
