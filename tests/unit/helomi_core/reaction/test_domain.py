from helomi_core.reaction import ReactionKind


def test_reaction_kind_enum():
    assert ReactionKind.GREETING == "greeting"
    assert ReactionKind.INTERRUPTED == "interrupted"
