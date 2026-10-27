"""Pytest bootstrap: put the project root on sys.path for package imports."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
