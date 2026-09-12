import rumps

from .item import MenuItem


class MenuGroup(rumps.MenuItem):
    def __init__(self, title: str) -> None:
        super().__init__(title=title)
        self._actions: dict[str, MenuItem] = {}

    def add_action(self, action: MenuItem) -> None:
        self.add(action)
        self._actions[action.id] = action

    def get_action(self, id: str) -> MenuItem:
        if id not in self._actions:
            raise ValueError(f"Menu item with id {id} not found")

        return self._actions[id]

    def set_enabled(self, enabled: bool) -> None:
        for action in self._actions.values():
            action.set_enabled(enabled)
