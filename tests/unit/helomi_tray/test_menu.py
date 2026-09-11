from unittest.mock import MagicMock

import pytest

from helomi_tray.app.menu import MenuAction, MenuGroup, MenuItem


def test_menu_item_properties_and_checked():
    # Item with id and checked=True
    item = MenuItem(title="Test", key="1", id="test_id", checked=True)
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
    item = MenuItem(title="No ID")
    with pytest.raises(ValueError, match="Menu item has no id"):
        _ = item.id


def test_menu_action_callbacks_and_enabled():
    cb = MagicMock()
    # Initially enabled=True
    action = MenuAction(
        title="Action",
        id="act_1",
        callback=cb,
        enabled=True,
        checked=False,
    )
    assert action.enabled is True
    assert action.callback is not None

    # Trigger callback
    action.callback(None)
    cb.assert_called_once_with(action)

    # set_enabled with same value returns unchanged
    assert action.set_enabled(True) is True

    # Disable action
    assert action.set_enabled(False) is False
    assert action.enabled is False
    assert action.callback is None

    # Toggle enabled with None
    assert action.set_enabled(None) is True
    assert action.enabled is True
    assert action.callback is not None


def test_menu_group_actions():
    group = MenuGroup(title="My Group")
    cb = MagicMock()
    action1 = MenuAction(title="Act 1", id="a1", callback=cb, enabled=True)
    action2 = MenuAction(title="Act 2", id="a2", callback=cb, enabled=True)

    group.add_action(action1)
    group.add_action(action2)

    assert group.get_action("a1") is action1
    assert group.get_action("a2") is action2

    with pytest.raises(ValueError, match="Menu action with id unknown not found"):
        group.get_action("unknown")

    # set_enabled disables all actions
    group.set_enabled(False)
    assert action1.enabled is False
    assert action2.enabled is False

    # set_enabled enables all actions
    group.set_enabled(True)
    assert action1.enabled is True
    assert action2.enabled is True
