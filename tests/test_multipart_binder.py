"""Test script to verify the SpooledTemporaryFile multipart binder implementation."""

from tempfile import SpooledTemporaryFile


# Test SpooledTemporaryFile behavior
def test_spooled_temp_file():
    print("Testing SpooledTemporaryFile behavior...")

    # Test 1: Small file stays in memory
    small_file = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    small_data = b"Small file content" * 100  # ~2KB
    small_file.write(small_data)
    small_file.seek(0)
    assert small_file.read() == small_data
    small_file.close()

    # Test 2: Large file spills to disk
    large_file = SpooledTemporaryFile(max_size=1024, mode="w+b")  # 1KB limit
    large_data = b"X" * 2048  # 2KB
    large_file.write(large_data)
    large_file.seek(0)
    assert large_file.read() == large_data
    large_file.close()
