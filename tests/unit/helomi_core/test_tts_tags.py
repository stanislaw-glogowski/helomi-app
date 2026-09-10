from helomi_core.tts import TTS_TAGS


def test_tts_tags_keys_and_values():
    """Verify TTS_TAGS contains valid bracketed tags and non-empty descriptions."""
    assert isinstance(TTS_TAGS, dict)
    assert len(TTS_TAGS) > 0

    for tag, desc in TTS_TAGS.items():
        assert tag.startswith("[")
        assert tag.endswith("]")
        assert len(tag) > 2
        assert isinstance(desc, str)
        assert len(desc.strip()) > 0


def test_tts_tags_instructions_coverage():
    """Verify all vocal tags mentioned in demo/prompts/instructions.md are present."""
    expected_tags = {
        "[laughter]": "Audible laugh",
        "[laughing]": "Audible laugh",
        "[giggle]": "Light giggle",
        "[snicker]": "Sarcastic snicker",
        "[sigh]": "Weary or relieved sigh",
        "[sighing]": "Weary or relieved sigh",
        "[gasp]": "Sharp inhale of surprise",
        "[breath]": "Audible breath or brief pause",
        "[throat-clearing]": "Clearing throat",
        "[cough]": "Slight cough",
        "[groan]": "Exasperated groan",
        "[whisper]": "Quiet whisper",
        "[whispering]": "Quiet whisper",
        "[shh]": "Hushed pause",
        "[um]": "Brief hesitation",
        "[uhm]": "Brief hesitation",
        "[pause]": "Brief silence or dramatic pause",
    }

    for tag, expected_desc in expected_tags.items():
        assert tag in TTS_TAGS
        assert TTS_TAGS[tag] == expected_desc


def test_tts_tags_keys_are_sorted():
    """Verify TTS_TAGS keys are defined in alphabetical order."""
    keys = list(TTS_TAGS.keys())
    assert keys == sorted(keys)
