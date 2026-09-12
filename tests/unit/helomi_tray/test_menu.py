from unittest.mock import MagicMock

import pytest

from helomi_tray.app.menu import MenuGroup, MenuItem


def test_menu_item_properties_and_checked():
    cb = MagicMock()
    # Item with id and checked=True
    item = MenuItem(title="Test", callback=cb, key="1", id="test_id", checked=True)
    assert item.title == "Test"
    assert item.key == "1"
    assert item.id == "test_id"
    assert item.checked is True

    # set_checked same value returns unchanged
    assert item.set_checked(True) is True

    # set_checked False
    assert item.set_checked(False) is False
    assert item.checked is False

    # set_checked None toggles
    assert item.set_checked(None) is True
    assert item.checked is True
    assert item.set_checked(None) is False
    assert item.checked is False


def test_menu_item_missing_id_raises():
    item = MenuItem(title="No ID", callback=lambda _: None)
    with pytest.raises(ValueError, match="Menu item has no id"):
        _ = item.id


def test_menu_item_callbacks_and_enabled():
    cb = MagicMock()
    # Initially enabled=True
    item = MenuItem(
        title="Action",
        id="act_1",
        callback=cb,
        enabled=True,
        checked=False,
    )
    assert item.enabled is True
    assert item.callback is not None

    # Trigger callback
    item.callback(None)
    cb.assert_called_once_with(item)

    # set_enabled with same value returns unchanged
    assert item.set_enabled(True) is True

    # Disable item
    assert item.set_enabled(False) is False
    assert item.enabled is False
    assert item.callback is None

    # Toggle enabled with None
    assert item.set_enabled(None) is True
    assert item.enabled is True
    assert item.callback is not None


def test_menu_group_actions():
    group = MenuGroup(title="My Group")
    cb = MagicMock()
    item1 = MenuItem(title="Act 1", id="a1", callback=cb, enabled=True)
    item2 = MenuItem(title="Act 2", id="a2", callback=cb, enabled=True)

    group.add_action(item1)
    group.add_action(item2)

    assert group.get_action("a1") is item1
    assert group.get_action("a2") is item2

    with pytest.raises(ValueError, match="Menu item with id unknown not found"):
        group.get_action("unknown")

    # set_enabled disables all actions
    group.set_enabled(False)
    assert item1.enabled is False
    assert item2.enabled is False

    # set_enabled enables all actions
    group.set_enabled(True)
    assert item1.enabled is True
    assert item2.enabled is True
