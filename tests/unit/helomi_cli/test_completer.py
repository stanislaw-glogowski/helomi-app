from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from helomi_cli.say.completer import SayCompleter


def test_say_completer_matches_bracketed_query():
    """Verify SayCompleter provides suggestions when reaction prefix is typed."""
    completer = SayCompleter()
    doc = Document("I am telling a joke [laugh")
    event = CompleteEvent()

    completions = list(completer.get_completions(doc, event))
    assert len(completions) > 0
    names = [c.text for c in completions]
    assert "laughter]" in names or "laughing]" in names


def test_say_completer_ignores_non_bracketed_text():
    """Verify SayCompleter returns empty when no opening bracket is present."""
    completer = SayCompleter()
    doc = Document("Hello world")
    event = CompleteEvent()

    assert list(completer.get_completions(doc, event)) == []


def test_say_completer_ignores_closed_bracket_or_spaces():
    """Verify SayCompleter skips closed bracket tags or queries with spaces."""
    completer = SayCompleter()
    event = CompleteEvent()

    doc_closed = Document("[laughter] next text")
    assert list(completer.get_completions(doc_closed, event)) == []

    doc_spaces = Document("[laugh ing")
    assert list(completer.get_completions(doc_spaces, event)) == []


def test_say_completer_with_runtime():
    """Verify SayCompleter can be initialized with Runtime instance."""
    from unittest.mock import MagicMock

    mock_runtime = MagicMock()
    completer = SayCompleter(mock_runtime)
    assert completer._runtime is mock_runtime
