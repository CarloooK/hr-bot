import sys
sys.path = [p for p in sys.path if 'ros' not in p.lower()]
import pytest
sys.exit(pytest.main(['-v', 'tests/']))
