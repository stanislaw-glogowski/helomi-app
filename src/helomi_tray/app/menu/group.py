import rumps

from .action import MenuAction


class MenuGroup(rumps.MenuItem):
    def __init__(self, title: str) -> None:
        super().__init__(title=title)
        self._actions: dict[str, MenuAction] = {}

    def add_action(self, action: MenuAction) -> None:
        self.add(action)
        self._actions[action.id] = action

    def get_action(self, id: str) -> MenuAction:
        if id not in self._actions:
            raise ValueError(f"Menu action with id {id} not found")

        return self._actions[id]

    def set_enabled(self, enabled: bool) -> None:
        for action in self._actions.values():
            action.set_enabled(enabled)
