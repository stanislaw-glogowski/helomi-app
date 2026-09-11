import rumps


class MenuItem(rumps.MenuItem):
    def __init__(
        self,
        title: str,
        key: str | None = None,
        id: str | None = None,
        checked: bool = False,
    ) -> None:
        super().__init__(
            title=title,
            key=key,
        )
        self._id = id

        if checked:
            self.state = 1

    @property
    def id(self) -> str:
        if self._id is None:
            raise ValueError("Menu item has no id")
        return self._id

    @property
    def checked(self) -> bool:
        return self.state == 1

    def set_checked(self, checked: bool | None) -> bool:
        if checked is None:
            checked = not self.checked
        elif checked == self.checked:
            return self.checked

        self.state = 1 if checked else 0

        return checked
