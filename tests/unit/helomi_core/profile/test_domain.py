from helomi_core.profile import ReactionKind


def test_reaction_kind_enum():
    assert ReactionKind.GREETING == "greeting"
    assert ReactionKind.INTERRUPTED == "interrupted"
