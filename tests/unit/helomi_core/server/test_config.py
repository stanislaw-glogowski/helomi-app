from helomi_core.server.config import ServerSettings


def test_server_settings_defaults() -> None:
    settings = ServerSettings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 4356
