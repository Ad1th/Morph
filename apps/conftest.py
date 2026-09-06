"""pytest configuration for the demo-app self-checks."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: statistical check that runs many trials (deselect with -m 'not slow')",
    )
