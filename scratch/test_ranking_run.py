import os
import datetime
import json
import sys

# Add current directory to path
sys.path.append(os.getcwd())

import main

# Mocking current_hour
class MockDateTime:
    @classmethod
    def now(cls, tz=None):
        return datetime.datetime(2026, 4, 26, 12, 0, 0, tzinfo=tz)

main.datetime.datetime = MockDateTime

sys.argv = ["main.py", "--hits", "2"]
print("Starting simulated autopost (Ranking mode - 12:00 JST)...")
try:
    main.main()
except Exception as e:
    print(f"Failed with error: {e}")
    import traceback
    traceback.print_exc()
