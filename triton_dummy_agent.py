
class UniversalMock:
    def __init__(self, name="Mock"): self._name = name
    def __getattr__(self, item): return self
    def __call__(self, *args, **kwargs): return self
_mock = UniversalMock()
def cdiv(x, y): return (x + y - 1) // y
def next_power_of_2(n): return 1
Config = _mock
compile = _mock
