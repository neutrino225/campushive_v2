from multiagent.agents.general_agent import RAGEngine


def test_extract_rector_from_text_simple_block():
    sample = """
    **Rector**
    Dr. Aftab Ahmad
    rector.nuces@nu.edu.pk
    """
    assert RAGEngine._extract_rector_from_text(sample) == "Dr. Aftab Ahmad"


def test_extract_rector_from_text_inline():
    sample = "The session was attended by Rector NUCES, Dr. Aftab Ahmad, and other officials."
    assert RAGEngine._extract_rector_from_text(sample) == "Dr. Aftab Ahmad"
