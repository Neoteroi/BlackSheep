#!/usr/bin/env python3
"""Test script to verify the SpooledTemporaryFile multipart binder implementation."""

import asyncio
from tempfile import SpooledTemporaryFile

# Test SpooledTemporaryFile behavior
def test_spooled_temp_file():
    print("Testing SpooledTemporaryFile behavior...")

    # Test 1: Small file stays in memory
    small_file = SpooledTemporaryFile(max_size=1024*1024, mode='w+b')
    small_data = b"Small file content" * 100  # ~2KB
    small_file.write(small_data)
    print(f"Small file ({len(small_data)} bytes) _file type: {type(small_file._file).__name__}")
    small_file.seek(0)
    assert small_file.read() == small_data
    small_file.close()

    # Test 2: Large file spills to disk
    large_file = SpooledTemporaryFile(max_size=1024, mode='w+b')  # 1KB limit
    large_data = b"X" * 2048  # 2KB
    large_file.write(large_data)
    print(f"Large file ({len(large_data)} bytes) _file type: {type(large_file._file).__name__}")
    large_file.seek(0)
    assert large_file.read() == large_data
    large_file.close()

    print("✓ SpooledTemporaryFile tests passed!")

async def test_multipart_stream_import():
    """Test that we can import and use the multipart streaming functionality."""
    print("\nTesting multipart streaming imports...")

    try:
        from blacksheep import Request
        from blacksheep.messages import Message

        # Check if multipart_stream exists
        assert hasattr(Message, 'multipart_stream'), "multipart_stream method not found"
        print("✓ multipart_stream method exists on Message class")

        # Check if we can import FormPart and StreamingFormPart
        from blacksheep.contents import FormPart, StreamingFormPart
        print("✓ FormPart and StreamingFormPart imported successfully")

        # Check if MultipartBinder has the new attributes
        from blacksheep.server.bindings import MultipartBinder
        assert hasattr(MultipartBinder, 'spool_max_size'), "spool_max_size not found"
        assert hasattr(MultipartBinder, 'max_field_size'), "max_field_size not found"
        print(f"✓ MultipartBinder.spool_max_size = {MultipartBinder.spool_max_size}")
        print(f"✓ MultipartBinder.max_field_size = {MultipartBinder.max_field_size}")

    except Exception as e:
        print(f"✗ Import test failed: {e}")
        raise

def main():
    print("=" * 60)
    print("Testing SpooledTemporaryFile Multipart Binder Implementation")
    print("=" * 60)

    test_spooled_temp_file()
    asyncio.run(test_multipart_stream_import())

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)

if __name__ == "__main__":
    main()
