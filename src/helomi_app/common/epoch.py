from typing import ClassVar


class EpochCoordinator:
    _current_epoch: ClassVar[int] = 1

    def __init_subclass__(cls):
        cls._current_epoch: int = 1

    @classmethod
    def current_epoch(cls) -> int:
        return cls._current_epoch

    @classmethod
    def bump(cls) -> int:
        cls._current_epoch += 1
        return cls._current_epoch

    @classmethod
    def is_stale(cls, epoch: int) -> bool:
        return epoch != cls.current_epoch()


class EpochEnvelope(EpochCoordinator):
    def __post_init__(self):
        epoch = getattr(self, "epoch", None)
        if epoch is None:
            object.__setattr__(self, "epoch", self.__class__.current_epoch())

    @property
    def is_valid(self) -> bool:
        epoch = getattr(self, "epoch", None)

        if not isinstance(epoch, int):
            return False

        return not self.__class__.is_stale(epoch)
