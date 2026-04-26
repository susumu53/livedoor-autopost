import os
import sys
from mgs_client import MGSClient

def test_mgs():
    client = MGSClient()
    print("Testing MGS search without keyword...")
    results = client.search_works(hits=3)
    if not results:
        print("No results found without keyword.")
    else:
        print(f"Found {len(results)} items.")
        for r in results:
            print(f"- {r['title']} ({r['source']})")

    print("\nTesting MGS search with keyword '競泳水着'...")
    results = client.search_works(keyword="競泳水着", hits=3)
    if not results:
        print("No results found with keyword.")
    else:
        print(f"Found {len(results)} items.")
        for r in results:
            print(f"- {r['title']} ({r['source']})")

if __name__ == "__main__":
    test_mgs()
