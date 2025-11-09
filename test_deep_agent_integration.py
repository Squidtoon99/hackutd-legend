#!/usr/bin/env python3
"""
Test script for the deep agent integration with Flask API.

This demonstrates the /tests/build endpoint that triggers the deep agent
to generate and execute verification plans.
"""
import requests
import time
import json
import sys

API_URL = "http://localhost:5000"


def test_build_endpoint():
    """Test the /tests/build endpoint."""
    print("Testing /tests/build endpoint...")

    # Test data
    payload = {
        "prompt": "Run test abc - verify memory is at least 16GB",
        "target_host": "raspberrypi",
        "server_id": "R200123A32",
    }

    print(f"\nSending request: {json.dumps(payload, indent=2)}")

    # Call the endpoint
    try:
        response = requests.post(f"{API_URL}/tests/build", json=payload, timeout=60)

        print(f"\nResponse status: {response.status_code}")
        print(f"Response body: {json.dumps(response.json(), indent=2)}")

        if response.status_code == 201:
            result = response.json()
            test_id = result.get("test_id")

            print(f"\n✅ Test created successfully!")
            print(f"Test ID: {test_id}")

            # Monitor the test streams
            if test_id:
                monitor_test_streams(test_id)

            return True
        else:
            print(f"\n❌ Test creation failed")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def monitor_test_streams(test_id: int, duration: int = 60):
    """Monitor the test streams for a given duration."""
    print(f"\n📡 Monitoring test {test_id} streams for {duration} seconds...")

    start_time = time.time()
    last_count = 0

    while time.time() - start_time < duration:
        try:
            response = requests.get(f"{API_URL}/tests/{test_id}/stream", timeout=5)

            if response.status_code == 200:
                streams = response.json()

                # Show new streams
                if len(streams) > last_count:
                    print(f"\n--- New events ({len(streams) - last_count}) ---")
                    for stream in streams[last_count:]:
                        event_type = stream.get("meta", {}).get("type", "unknown")
                        message = stream.get("message", "")
                        print(f"[{event_type}] {message}")

                    last_count = len(streams)

            time.sleep(2)

        except Exception as e:
            print(f"Error monitoring streams: {e}")
            break

    print(f"\n✅ Monitoring complete. Total events: {last_count}")


def test_missing_fields():
    """Test validation of required fields."""
    print("\n\nTesting validation...")

    # Test missing prompt
    response = requests.post(
        f"{API_URL}/tests/build", json={"target_host": "test.local"}, timeout=10
    )
    assert response.status_code == 400, "Should fail without prompt"
    print("✅ Correctly validates missing prompt")

    # Test missing target_host
    response = requests.post(
        f"{API_URL}/tests/build", json={"prompt": "test"}, timeout=10
    )
    assert response.status_code == 400, "Should fail without target_host"
    print("✅ Correctly validates missing target_host")

    # Test empty body
    response = requests.post(f"{API_URL}/tests/build", timeout=10)
    assert response.status_code == 415, "Should fail with empty body"
    print("✅ Correctly validates empty request body")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Deep Agent Integration Test Suite")
    print("=" * 60)

    # Check if API is running
    try:
        response = requests.get(f"{API_URL}/", timeout=5)
        print(f"✅ API is running at {API_URL}")
    except Exception as e:
        print(f"❌ API is not running at {API_URL}: {e}")
        print("Please start the Flask API first: python api.py")
        sys.exit(1)

    # Run validation tests
    test_missing_fields()

    # Run main test
    success = test_build_endpoint()

    print("\n" + "=" * 60)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
