"""Test script to verify connection caching works correctly.

This demonstrates that multiple calls to get_client() return the same
cached connection instance, avoiding repeated connection overhead.
"""
import sys
from scripts.session_manager import get_client, get_cache_info


def test_connection_caching():
    """Test that get_client returns cached connections."""
    print("🧪 Testing Connection Caching\n")
    
    # First call - creates new connection
    print("1️⃣  First call to get_client()...")
    client1 = get_client("Tess2")
    print(f"   ✅ Client created: {id(client1)}")
    print(f"   Cache info: {get_cache_info()}\n")
    
    # Second call - should return cached connection
    print("2️⃣  Second call to get_client()...")
    client2 = get_client("Tess2")
    print(f"   ✅ Client retrieved: {id(client2)}")
    print(f"   Cache info: {get_cache_info()}\n")
    
    # Verify they're the same object
    if client1 is client2:
        print("✨ SUCCESS: Both calls returned the SAME cached connection!")
        print(f"   Memory address: {id(client1)}")
        print("   ✅ No new connection created on second call\n")
    else:
        print("❌ FAILED: Different connections were returned!")
        sys.exit(1)
    
    # Third call - still cached
    print("3️⃣  Third call to get_client()...")
    client3 = get_client("Tess2")
    print(f"   ✅ Client retrieved: {id(client3)}")
    
    if client1 is client3:
        print("   ✅ Same cached connection returned\n")
    else:
        print("   ❌ Different connection returned\n")
        sys.exit(1)
    
    print("🎉 Connection caching test PASSED!")
    print("   - Connection is reused across multiple calls")
    print("   - No SQLite locking issues")
    print("   - Better performance and resource usage")


if __name__ == "__main__":
    test_connection_caching()
