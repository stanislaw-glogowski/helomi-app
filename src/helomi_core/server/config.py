from helomi_common import BaseConfig


class ServerSettings(BaseConfig):
    host: str = "127.0.0.1"
    port: int = 4356
