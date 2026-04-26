import os
import datetime
import json
import sys
from main import main as autopost_main

# Simulate 13:00 (Odd hour -> Beauty Analysis)
class MockDateTime:
    @classmethod
    def now(cls, tz=None):
        # 2026-04-26 13:00:00 JST
        return datetime.datetime(2026, 4, 26, 13, 0, 0, tzinfo=tz)

import datetime
datetime.datetime = MockDateTime

# Override sys.argv
sys.argv = ["main.py", "--hits", "1"]

print("Starting simulated autopost (Beauty Analysis mode)...")
autopost_main()
