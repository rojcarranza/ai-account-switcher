import os
import sys

# The documented test command sets no PYTHONPATH, so make src/ importable here.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
