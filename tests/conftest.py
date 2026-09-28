import os
import sys

CI_GUARD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ci_guard")
if CI_GUARD_DIR not in sys.path:
    sys.path.insert(0, CI_GUARD_DIR)
