import ticket_automation


def test_package_is_importable() -> None:
    assert ticket_automation.__version__ == "0.1.0"
