from unittest.mock import MagicMock, patch

import AppKit

from helomi_tray.app.windows.tts import (
    TTS_TAGS,
    ComposeTextView,
    ComposeTextViewDelegate,
    RoundedLayoutManager,
    TagButton,
    TagButtonsContainer,
    TTSWindow,
)


def test_tts_tags_content():
    """Verify TTS tags dict includes expected vocal emotions and descriptions."""
    assert "[laughter]" in TTS_TAGS
    assert "[sigh]" in TTS_TAGS
    assert "[whisper]" in TTS_TAGS
    assert "[pause]" in TTS_TAGS
    assert TTS_TAGS["[pause]"] == "Brief silence or dramatic pause"
    assert list(TTS_TAGS.keys()) == sorted(TTS_TAGS.keys())


def test_compose_text_view_find_tag_range_and_backspace():
    """Verify _find_tag_range finds tag boundaries and backspace deletes entire tag."""
    tv = ComposeTextView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 200, 100))

    # 1. Cursor immediately after closing ']' of valid tag
    tv.setString_("Hello [applause] world")
    assert tv._find_tag_range(tv.string(), 16) == (6, 16)

    # 2. Cursor inside tag
    assert tv._find_tag_range(tv.string(), 10) == (6, 16)
    assert tv._find_tag_range(tv.string(), 7) == (6, 16)

    # 3. Cursor at start of tag or outside tag
    assert tv._find_tag_range(tv.string(), 6) is None
    assert tv._find_tag_range(tv.string(), 5) is None
    assert tv._find_tag_range(tv.string(), 20) is None
    assert tv._find_tag_range(tv.string(), 0) is None
    assert tv._find_tag_range(tv.string(), 999) is None

    # 4. Unknown tag not in TTS_TAGS
    tv.setString_("Hello [unknown] world")
    assert tv._find_tag_range(tv.string(), 15) is None

    # 5. _handle_backspace_tag deletes entire tag when cursor is at ']'
    tv.setString_("Hello [laughter]")
    tv.setSelectedRange_(AppKit.NSMakeRange(16, 0))
    assert tv._handle_backspace_tag() is True
    assert tv.string() == "Hello "

    # 6. _handle_backspace_tag returns False when selection length > 0
    tv.setString_("Hello [laughter]")
    tv.setSelectedRange_(AppKit.NSMakeRange(6, 10))
    assert tv._handle_backspace_tag() is False

    # 7. _handle_backspace_tag returns False on regular text
    tv.setString_("Hello world")
    tv.setSelectedRange_(AppKit.NSMakeRange(5, 0))
    assert tv._handle_backspace_tag() is False

    # 8. deleteBackward_ calls _handle_backspace_tag
    tv.setString_("Say [sigh]")
    tv.setSelectedRange_(AppKit.NSMakeRange(10, 0))
    tv.deleteBackward_(None)
    assert tv.string() == "Say "


def test_compose_text_view_perform_key_equivalent():
    """Verify performKeyEquivalent_ handles edit shortcuts, enter, and window close."""
    tv = ComposeTextView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 200, 100))
    send_called = False

    def on_send():
        nonlocal send_called
        send_called = True

    tv.send_action = on_send

    def make_event(char, flags=AppKit.NSEventModifierFlagCommand, chars_ign=None):
        event = MagicMock()
        event.modifierFlags.return_value = flags
        event.characters.return_value = char
        event.charactersIgnoringModifiers.return_value = chars_ign or char
        return event

    # 1. Cmd+V calls paste_
    tv.paste_ = MagicMock()
    assert tv.performKeyEquivalent_(make_event("v")) is True
    tv.paste_.assert_called_once_with(None)

    # 2. Cmd+C calls copy_
    tv.copy_ = MagicMock()
    assert tv.performKeyEquivalent_(make_event("c")) is True
    tv.copy_.assert_called_once_with(None)

    # 3. Cmd+X calls cut_
    tv.cut_ = MagicMock()
    assert tv.performKeyEquivalent_(make_event("x")) is True
    tv.cut_.assert_called_once_with(None)

    # 4. Cmd+A calls selectAll_
    tv.selectAll_ = MagicMock()
    assert tv.performKeyEquivalent_(make_event("a")) is True
    tv.selectAll_.assert_called_once_with(None)

    # 5. Cmd+Z calls undo
    mock_um = MagicMock()
    mock_um.canUndo.return_value = True
    mock_um.canRedo.return_value = True
    tv.undoManager = MagicMock(return_value=mock_um)
    assert tv.performKeyEquivalent_(make_event("z")) is True
    mock_um.undo.assert_called_once()

    # 6. Cmd+Shift+Z calls redo
    flags_shift = AppKit.NSEventModifierFlagCommand | AppKit.NSEventModifierFlagShift
    assert (
        tv.performKeyEquivalent_(make_event("Z", flags=flags_shift, chars_ign="z"))
        is True
    )
    mock_um.redo.assert_called_once()

    # 7. Cmd+Z without undoManager or when canUndo is False
    mock_um.canUndo.return_value = False
    mock_um.canRedo.return_value = False
    tv.performKeyEquivalent_(make_event("z"))
    tv.performKeyEquivalent_(make_event("Z", flags=flags_shift, chars_ign="z"))
    tv.undoManager = MagicMock(return_value=None)
    tv.performKeyEquivalent_(make_event("z"))
    tv.performKeyEquivalent_(make_event("Z", flags=flags_shift, chars_ign="z"))

    # 8. Cmd+W closes window
    mock_win = MagicMock()
    with patch.object(tv, "window", return_value=mock_win):
        assert tv.performKeyEquivalent_(make_event("w")) is True
        mock_win.performClose_.assert_called_once_with(None)

    # 9. Cmd+W without window
    with patch.object(tv, "window", return_value=None):
        assert tv.performKeyEquivalent_(make_event("w")) is True

    # 10. Cmd+Enter triggers send_action
    assert tv.performKeyEquivalent_(make_event("\r")) is True
    assert send_called is True

    # 11. Cmd+Enter with \n
    send_called = False
    assert tv.performKeyEquivalent_(make_event("\n")) is True
    assert send_called is True

    # 12. Cmd+Enter without send_action
    tv.send_action = None
    tv.performKeyEquivalent_(make_event("\r"))

    # 13. Regular key delegates to super
    with patch("helomi_tray.app.windows.tts.objc.super") as mock_super:
        mock_super.return_value.performKeyEquivalent_.return_value = False
        res = tv.performKeyEquivalent_(make_event("a", flags=0))
        assert res is False
        mock_super.return_value.performKeyEquivalent_.assert_called_once()


def test_compose_text_view_key_down():
    """Verify keyDown_ handles Cmd+Enter, Cmd+W, edit fallbacks, and regular keys."""
    tv = ComposeTextView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 200, 100))
    send_called = False

    def on_send():
        nonlocal send_called
        send_called = True

    tv.send_action = on_send

    def make_event(char, flags=AppKit.NSEventModifierFlagCommand, chars_ign=None):
        event = MagicMock()
        event.modifierFlags.return_value = flags
        event.characters.return_value = char
        event.charactersIgnoringModifiers.return_value = chars_ign or char
        return event

    # 1. Cmd+Enter triggers send_action
    tv.keyDown_(make_event("\r"))
    assert send_called is True

    # 2. Cmd+Enter with \n also triggers send_action
    send_called = False
    tv.keyDown_(make_event("\n"))
    assert send_called is True

    # 3. Cmd+Enter without send_action does not crash
    tv.send_action = None
    with patch("helomi_tray.app.windows.tts.objc.super") as mock_super:
        tv.keyDown_(make_event("\r"))
        mock_super.assert_not_called()

    # 4. Cmd+W closes window
    mock_window = MagicMock()
    with patch.object(tv, "window", return_value=mock_window):
        tv.keyDown_(make_event("w"))
        mock_window.performClose_.assert_called_once_with(None)

    # 5. Cmd+W with no window does not crash
    with patch.object(tv, "window", return_value=None):
        tv.keyDown_(make_event("w"))

    # 6. Cmd+V in keyDown_
    tv.paste_ = MagicMock()
    tv.keyDown_(make_event("v"))
    tv.paste_.assert_called_once_with(None)

    # 7. Cmd+C in keyDown_
    tv.copy_ = MagicMock()
    tv.keyDown_(make_event("c"))
    tv.copy_.assert_called_once_with(None)

    # 8. Cmd+X in keyDown_
    tv.cut_ = MagicMock()
    tv.keyDown_(make_event("x"))
    tv.cut_.assert_called_once_with(None)

    # 9. Cmd+A in keyDown_
    tv.selectAll_ = MagicMock()
    tv.keyDown_(make_event("a"))
    tv.selectAll_.assert_called_once_with(None)

    # 10. Cmd+Z in keyDown_
    mock_um = MagicMock()
    mock_um.canUndo.return_value = True
    mock_um.canRedo.return_value = True
    tv.undoManager = MagicMock(return_value=mock_um)
    tv.keyDown_(make_event("z"))
    mock_um.undo.assert_called_once()

    flags_shift = AppKit.NSEventModifierFlagCommand | AppKit.NSEventModifierFlagShift
    tv.keyDown_(make_event("Z", flags=flags_shift, chars_ign="z"))
    mock_um.redo.assert_called_once()

    # 11. Cmd+Z without undoManager or when canUndo is False
    mock_um.canUndo.return_value = False
    mock_um.canRedo.return_value = False
    tv.keyDown_(make_event("z"))
    tv.keyDown_(make_event("Z", flags=flags_shift, chars_ign="z"))
    tv.undoManager = MagicMock(return_value=None)
    tv.keyDown_(make_event("z"))
    tv.keyDown_(make_event("Z", flags=flags_shift, chars_ign="z"))

    # 12. Key event with None characters does not crash
    mock_event_none = MagicMock()
    mock_event_none.characters.return_value = None
    mock_event_none.charactersIgnoringModifiers.return_value = None
    mock_event_none.modifierFlags.return_value = 0
    with patch("helomi_tray.app.windows.tts.objc.super") as mock_super:
        tv.keyDown_(mock_event_none)
        mock_super.return_value.keyDown_.assert_called_once_with(mock_event_none)

    # 13. Regular key falls back to super.keyDown_
    mock_event_regular = MagicMock()
    mock_event_regular.characters.return_value = "a"
    mock_event_regular.charactersIgnoringModifiers.return_value = "a"
    mock_event_regular.modifierFlags.return_value = 0
    with patch("helomi_tray.app.windows.tts.objc.super") as mock_super:
        tv.keyDown_(mock_event_regular)
        mock_super.return_value.keyDown_.assert_called_once_with(mock_event_regular)


def test_rounded_layout_manager():
    """Verify RoundedLayoutManager draws rounded pill paths and returns rect_array."""
    lm = RoundedLayoutManager.alloc().init()
    rects = [AppKit.NSMakeRect(10, 10, 50, 20)]
    color = AppKit.NSColor.textColor()
    res = lm.fillBackgroundRectArray_count_forCharacterRange_color_(
        rects, 1, AppKit.NSMakeRange(0, 5), color
    )
    assert res == rects


def test_tag_button_and_container():
    """Verify TagButton custom drawing and TagButtonsContainer flow wrapping."""
    # 1. TagButton custom drawRect_
    btn = TagButton.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 80, 20))
    btn.setTitle_("[sigh]")

    # Test normal drawing
    with patch.object(btn, "isHighlighted", return_value=False):
        btn.drawRect_(btn.bounds())

    # Test highlighted drawing
    with patch.object(btn, "isHighlighted", return_value=True):
        btn.drawRect_(btn.bounds())

    # 2. TagButtonsContainer
    container = TagButtonsContainer.alloc().initWithFrame_(
        AppKit.NSMakeRect(0, 0, 520, 120)
    )
    assert container.isFlipped() is True

    # Empty buttons does not crash
    container.buttons = []
    container.relayout_buttons()

    # Wrapped layout with multiple buttons
    for tag in ["[sigh]", "[applause]", "[breath]", "[chuckle]"]:
        b = TagButton.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 10, 20))
        b.setTitle_(tag)
        container.buttons.append(b)
        container.addSubview_(b)

    container.relayout_buttons()
    assert container.buttons[0].frame().size.width > 0

    # Resize subviews triggers relayout
    container.setFrameSize_(AppKit.NSMakeSize(100, 120))
    container.resizeSubviewsWithOldSize_(AppKit.NSMakeSize(520, 120))


def test_compose_text_view_delegate_highlight_tags():
    """Verify ComposeTextViewDelegate applies tag styling and restores attrs."""
    delegate = ComposeTextViewDelegate(
        tags=["[sigh]", "[applause]"],
        on_text_change=None,
    )
    tv = ComposeTextView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 200, 100))

    # 1. Empty text -> does nothing
    tv.setString_("")
    delegate.highlight_tags(tv)

    # 2. Text with emotion tag gets background attribute on tag range
    tv.setString_("Hello [sigh] world")
    delegate.highlight_tags(tv)
    ts = tv.textStorage()
    assert ts is not None

    val_tag, _ = ts.attribute_atIndex_effectiveRange_(
        AppKit.NSBackgroundColorAttributeName, 7, None
    )
    assert val_tag is not None

    val_plain, _ = ts.attribute_atIndex_effectiveRange_(
        AppKit.NSBackgroundColorAttributeName, 0, None
    )
    assert val_plain is None

    # 3. Typing attributes restored with text color
    typing_attrs = tv.typingAttributes()
    assert typing_attrs.get(AppKit.NSForegroundColorAttributeName) is not None


def test_compose_text_view_delegate_text_did_change():
    """Verify textDidChange_ triggers tag highlighting and notifies change."""
    text_changed = False

    def on_change():
        nonlocal text_changed
        text_changed = True

    delegate = ComposeTextViewDelegate(
        tags=["[sigh]"],
        on_text_change=on_change,
    )
    tv = ComposeTextView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 200, 100))
    tv.setString_("Say [sigh]")

    notification = MagicMock()
    notification.object.return_value = tv

    delegate.textDidChange_(notification)
    assert text_changed is True

    # Delegate without on_text_change does not crash
    delegate.on_text_change = None
    delegate.textDidChange_(notification)


def test_compose_text_view_backspace_on_bracket():
    """Verify backspace deletes full emotion tag when cursor encounters tag."""
    win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        AppKit.NSMakeRect(0, 0, 400, 200),
        AppKit.NSWindowStyleMaskTitled,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    tv = ComposeTextView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 400, 200))
    win.contentView().addSubview_(tv)
    win.makeKeyAndOrderFront_(None)

    tv.setString_("Hello [applause]")
    tv.setSelectedRange_(AppKit.NSMakeRange(16, 0))

    event_name = (
        "keyEventWithType_location_modifierFlags_timestamp_"
        "windowNumber_context_characters_charactersIgnoringModifiers_"
        "isARepeat_keyCode_"
    )
    make_event = getattr(AppKit.NSEvent, event_name)
    event = make_event(
        AppKit.NSEventTypeKeyDown,
        AppKit.NSMakePoint(0, 0),
        0,
        0,
        win.windowNumber(),
        None,
        "\x7f",
        "\x7f",
        False,
        51,
    )
    tv.keyDown_(event)
    assert tv.string() == "Hello "


def test_tts_window_lifecycle_and_ui():
    """Verify TTSWindow initializes correctly, shows, closes, and triggers on_close."""
    sent_text: list[str] = []
    closed = False

    def on_close():
        nonlocal closed
        closed = True

    # Test both direct instantiation and .create factory
    window_ctrl = TTSWindow(
        on_send=lambda t: sent_text.append(t),
        on_close=on_close,
    )
    factory_ctrl = TTSWindow.create(on_close=on_close)
    assert factory_ctrl.window.title() == "Text to Speech"

    assert window_ctrl.window.title() == "Text to Speech"
    assert window_ctrl.status_label.stringValue() == "Ready"
    assert window_ctrl.window.canBecomeKeyWindow() is True

    # Test show() keeps accessory policy and focuses (never elevated to regular)
    window_ctrl.show()
    app = AppKit.NSApplication.sharedApplication()
    assert app.activationPolicy() == AppKit.NSApplicationActivationPolicyAccessory

    # Test close() keeps accessory policy and triggers callback
    window_ctrl.close()
    assert app.activationPolicy() == AppKit.NSApplicationActivationPolicyAccessory
    assert closed is True

    # Test windowWillClose_ delegate method keeps accessory policy
    # and triggers callback
    closed = False
    window_ctrl.windowWillClose_(None)
    assert app.activationPolicy() == AppKit.NSApplicationActivationPolicyAccessory
    assert closed is True

    # Test tag buttons created for each tag
    assert len(window_ctrl.tag_buttons) == len(TTS_TAGS)
    first_btn = window_ctrl.tag_buttons[0]
    assert first_btn.title() == next(iter(TTS_TAGS.keys()))
    assert isinstance(first_btn, TagButton)
    assert len(window_ctrl.tag_container.buttons) == len(TTS_TAGS)

    # Test clicking tag button inserts tag at cursor and spaces properly
    window_ctrl.text_view.setString_("Hello")
    window_ctrl.text_view.setSelectedRange_(AppKit.NSMakeRange(5, 0))
    window_ctrl.tagButtonClicked_(first_btn)
    expected_text = f"Hello {first_btn.title()} "
    assert window_ctrl.text_view.string() == expected_text

    # Test close_btn and closeClicked_
    assert window_ctrl.close_btn.title() == "Close"
    closed = False
    window_ctrl._on_close = on_close
    window_ctrl.show()
    window_ctrl.closeClicked_(None)
    assert app.activationPolicy() == AppKit.NSApplicationActivationPolicyAccessory
    assert closed is True

    # Test window without on_close callback does not crash
    window_ctrl._on_close = None
    window_ctrl.close()
    window_ctrl.windowWillClose_(None)
    window_ctrl.closeClicked_(None)
    window_ctrl.close()
    window_ctrl.windowWillClose_(None)
    window_ctrl.closeClicked_(None)

    # Test clearClicked_ and clear()
    window_ctrl.text_view.setString_("Some text")
    window_ctrl.clearClicked_(None)
    assert window_ctrl.text_view.string() == ""
    assert window_ctrl.status_label.stringValue() == "Cleared"

    window_ctrl.text_view.setString_("Other text")
    window_ctrl.clear()
    assert window_ctrl.text_view.string() == ""
    assert window_ctrl.status_label.stringValue() == "Cleared"

    # Test _handle_text_change resets status from Cleared/Sent to Ready
    window_ctrl.status_label.setStringValue_("Cleared")
    window_ctrl._handle_text_change()
    assert window_ctrl.status_label.stringValue() == "Ready"

    window_ctrl.status_label.setStringValue_("Sent")
    window_ctrl._handle_text_change()
    assert window_ctrl.status_label.stringValue() == "Ready"

    # Other status is not overwritten
    window_ctrl.status_label.setStringValue_("Speaking…")
    window_ctrl._handle_text_change()
    assert window_ctrl.status_label.stringValue() == "Speaking…"


def test_tts_window_do_send():
    """Verify do_send handles empty text, valid text, callbacks, and errors."""
    sent_text: list[str] = []
    window_ctrl = TTSWindow.create(on_send=lambda t: sent_text.append(t))

    # 1. Empty or whitespace text does nothing
    window_ctrl.text_view.setString_("   \n\t  ")
    window_ctrl.do_send()
    assert sent_text == []
    assert window_ctrl.status_label.stringValue() == "Ready"

    # 2. Non-empty text dispatches and updates status
    window_ctrl.text_view.setString_("Hello world [laughter]")
    window_ctrl.sendClicked_(None)
    assert sent_text == ["Hello world [laughter]"]
    assert window_ctrl.status_label.stringValue() == "Sent"

    # 3. Exception in send callback sets error status
    def fail_send(_: str):
        raise RuntimeError("Speech failed")

    window_ctrl._on_send = fail_send
    window_ctrl.text_view.setString_("Will fail")
    window_ctrl.do_send()
    assert "Error: Speech failed" in window_ctrl.status_label.stringValue()

    # 4. window_ctrl without on_send callback does not fail
    window_ctrl._on_send = None
    window_ctrl.do_send()
    assert window_ctrl.status_label.stringValue() == "Sent"


def test_tts_window_handle_synthesis_ready_and_events():
    """Verify handle_event and on_synthesis_ready enable save button and store audio."""
    from helomi_core.audio import RawAudio
    from helomi_core.pipeline import SynthesisReadyEvent

    window_ctrl = TTSWindow()
    assert window_ctrl.save_btn.title() == "Save to …"
    assert window_ctrl.save_btn.isEnabled() is False

    mock_audio = MagicMock(spec=RawAudio)
    event = SynthesisReadyEvent(
        profile_id="test_profile",
        text="Hello",
        audio=mock_audio,
    )

    # 1. Non-SynthesisReady event is ignored
    window_ctrl.handle_event("other_event")
    assert window_ctrl._current_audio is None
    assert window_ctrl.save_btn.isEnabled() is False

    # 2. SynthesisReady event stores audio and enables save button on main thread
    window_ctrl.status_label.setStringValue_("Speaking…")
    window_ctrl.handle_event(event)
    assert window_ctrl._current_audio is mock_audio
    assert window_ctrl._current_profile_id == "test_profile"
    assert window_ctrl.save_btn.isEnabled() is True
    assert window_ctrl.status_label.stringValue() == "Ready"

    # 3. SynthesisReady with audio=None does not enable save button
    window_ctrl.save_btn.setEnabled_(False)
    none_audio_event = SynthesisReadyEvent(
        profile_id="test_profile",
        text="Empty",
        audio=None,
    )
    window_ctrl.on_synthesis_ready(none_audio_event)
    assert window_ctrl.save_btn.isEnabled() is False

    # 4. Threaded execution uses PyObjCTools.AppHelper.callAfter
    with (
        patch("threading.current_thread") as mock_current_thread,
        patch("threading.main_thread") as mock_main_thread,
        patch("PyObjCTools.AppHelper.callAfter") as mock_call_after,
    ):
        mock_current_thread.return_value = MagicMock()
        mock_main_thread.return_value = MagicMock()
        window_ctrl.on_synthesis_ready(event)
        mock_call_after.assert_called_once_with(window_ctrl._enable_save)


def test_tts_window_do_save():
    """Verify do_save prompts SaveFileDialog, writes audio, and handles cancel/error."""
    from pathlib import Path

    from helomi_core.audio import RawAudio

    window_ctrl = TTSWindow(get_profile_id=lambda: "fallback_profile")

    # 1. No audio -> does nothing
    with patch("helomi_tray.app.windows.tts.SaveFileDialog") as mock_dialog:
        window_ctrl.saveClicked_(None)
        mock_dialog.assert_not_called()

    # 2. User cancels save dialog
    mock_audio = MagicMock(spec=RawAudio)
    window_ctrl._current_audio = mock_audio
    window_ctrl._current_profile_id = "agent_1"

    with patch("helomi_tray.app.windows.tts.SaveFileDialog") as mock_dialog_cls:
        mock_dialog = mock_dialog_cls.return_value
        mock_dialog.open.return_value = None

        window_ctrl.do_save()
        mock_dialog_cls.assert_called_once()
        name_arg = mock_dialog_cls.call_args.kwargs["default_name"]
        assert name_arg.startswith("agent_1_")
        assert name_arg.endswith(".wav")

    # 3. User selects file and save succeeds
    target_path = Path("/tmp/speech_output.wav")
    with (
        patch("helomi_tray.app.windows.tts.SaveFileDialog") as mock_dialog_cls,
        patch("helomi_tray.app.windows.tts.AudioFile") as mock_audio_file,
    ):
        mock_dialog = mock_dialog_cls.return_value
        mock_dialog.open.return_value = target_path

        window_ctrl.do_save()
        mock_audio_file.assert_called_once_with(target_path)
        mock_audio_file.return_value.write.assert_called_once_with(mock_audio)
        assert window_ctrl.status_label.stringValue() == "Saved: speech_output.wav"

    # 4. Fallback profile from get_profile_id and default "tts"
    window_ctrl._current_profile_id = None
    with patch("helomi_tray.app.windows.tts.SaveFileDialog") as mock_dialog_cls:
        mock_dialog_cls.return_value.open.return_value = None
        window_ctrl.do_save()
        name_arg = mock_dialog_cls.call_args.kwargs["default_name"]
        assert name_arg.startswith("fallback_profile_")

    window_ctrl._get_profile_id = None
    with patch("helomi_tray.app.windows.tts.SaveFileDialog") as mock_dialog_cls:
        mock_dialog_cls.return_value.open.return_value = None
        window_ctrl.do_save()
        name_arg = mock_dialog_cls.call_args.kwargs["default_name"]
        assert name_arg.startswith("tts_")

    # 5. AudioFile write error updates status
    with (
        patch("helomi_tray.app.windows.tts.SaveFileDialog") as mock_dialog_cls,
        patch("helomi_tray.app.windows.tts.AudioFile") as mock_audio_file,
    ):
        mock_dialog_cls.return_value.open.return_value = target_path
        mock_audio_file.return_value.write.side_effect = OSError("Disk full")

        window_ctrl.do_save()
        assert window_ctrl.status_label.stringValue() == "Error: Disk full"


def test_tts_window_resets_on_clear_and_send():
    """Verify clear and do_send reset current audio and disable save button."""
    from helomi_core.audio import RawAudio

    window_ctrl = TTSWindow()
    mock_audio = MagicMock(spec=RawAudio)
    window_ctrl._current_audio = mock_audio
    window_ctrl._current_profile_id = "test"
    window_ctrl.save_btn.setEnabled_(True)

    # 1. clear resets state
    window_ctrl.clear()
    assert window_ctrl._current_audio is None
    assert window_ctrl._current_profile_id is None
    assert window_ctrl._current_timestamp is None
    assert window_ctrl.save_btn.isEnabled() is False

    # 2. do_send resets state
    window_ctrl._current_audio = mock_audio
    window_ctrl._current_profile_id = "test"
    window_ctrl.save_btn.setEnabled_(True)
    window_ctrl.text_view.setString_("Speak this")
    window_ctrl.do_send()
    assert window_ctrl._current_audio is None
    assert window_ctrl._current_profile_id is None
    assert window_ctrl._current_timestamp is None
    assert window_ctrl.save_btn.isEnabled() is False
