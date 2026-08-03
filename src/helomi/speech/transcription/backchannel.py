import re


class ListenerBackchannelDetector:
    """Recognize only unambiguous listener backchannels during playback."""

    _BACKCHANNELS = frozenset({"mhm", "mm hm", "uhum", "aha"})
    _HYPHENS = re.compile(r"[-\u2013\u2014]")
    _WHITESPACE = re.compile(r"\s+")

    @classmethod
    def normalize(cls, text: str) -> str:
        normalized = cls._HYPHENS.sub(" ", text.casefold())
        normalized = cls._WHITESPACE.sub(" ", normalized)
        return normalized.strip(".?!,;: \t\n")

    def is_backchannel(self, text: str) -> bool:
        return self.normalize(text) in self._BACKCHANNELS
