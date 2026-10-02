from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Final

DECORATORS_ATTR_NAME: Final[str] = "__helomi_decorators__"


class LifecycleHookKind(StrEnum):
    MOUNT = auto()
    UNMOUNT = auto()
    RUN = auto()


@dataclass(frozen=True, slots=True)
class LifecycleHook:
    name: str
    order: int


def resolve_lifecycle_hooks(
    target: object, kind: LifecycleHookKind
) -> tuple[LifecycleHook, ...]:
    hooks: dict[str, LifecycleHook] = {}

    for component_class in reversed(type.mro(target.__class__)):
        for name, method in vars(component_class).items():
            if not callable(method):
                continue

            order = (
                definitions.get(kind, None)
                if (definitions := getattr(method, DECORATORS_ATTR_NAME, None))
                and isinstance(definitions, dict)
                else None
            )

            if not isinstance(order, int):
                # An override without the decorator intentionally disables the
                # inherited hook with the same name.
                hooks.pop(name, None)
                continue

            hooks[name] = LifecycleHook(
                name=name,
                order=order,
            )

    return tuple(sorted(hooks.values(), key=lambda hook: hook.order))


def on_mount(*, order: int = 0):
    return _define_decorator(LifecycleHookKind.MOUNT, order=order)


def on_unmount(*, order: int = 0):
    return _define_decorator(LifecycleHookKind.UNMOUNT, order=order)


def on_run(*, order: int = 0):
    return _define_decorator(LifecycleHookKind.RUN, order=order)


def _define_decorator(
    kind: LifecycleHookKind, *, order: int = 0
) -> Callable[[Callable], Callable]:
    def _hook(method: Callable) -> Callable:
        match getattr(method, DECORATORS_ATTR_NAME, None):
            case None:
                object.__setattr__(
                    method,
                    DECORATORS_ATTR_NAME,
                    {
                        kind: order,
                    },
                )
            case dict(definitions):
                if kind in definitions:
                    raise ValueError(f"Hook '{kind}' already defined")
                definitions[kind] = order

        return method

    return _hook
