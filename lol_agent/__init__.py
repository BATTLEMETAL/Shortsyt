# lol_agent package initialization
# Compatibility shim for Google Auth pickled credentials across Python / library versions
import sys
import types

try:
    import google.auth._regional_access_boundary_utils
except ImportError:
    class DummyRAB:
        def __init__(self, *args, **kwargs):
            pass

        def __setstate__(self, state):
            if isinstance(state, dict):
                self.__dict__.update(state)

        def apply_headers(self, headers):
            pass

    _rab_mod = types.ModuleType("google.auth._regional_access_boundary_utils")
    _rab_mod.DummyRAB = DummyRAB
    _rab_mod._RegionalAccessBoundaryManager = DummyRAB
    _rab_mod._RegionalAccessBoundaryData = DummyRAB
    _rab_mod._RegionalAccessBoundaryRefreshManager = DummyRAB
    sys.modules["google.auth._regional_access_boundary_utils"] = _rab_mod
