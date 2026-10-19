"""Extractor interface. Any reader that fills a FileExtraction can be scored by the same harness and gate,
so an Azure AI Document Intelligence or AI Builder model can be dropped in next to the local ones."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Cite:
    page: int  # 1 based
    line: str
    conf: float  # 0 to 1


@dataclass
class Value:
    value: object
    cite: Cite | None = None
    validated: bool = False

    @property
    def conf(self) -> float:
        if self.cite is None:
            return 0.0
        return 0.99 if self.validated else self.cite.conf


@dataclass
class FileExtraction:
    file_id: str
    extractor: str
    page_kinds: list = field(default_factory=list)  # [{"page": 1, "kind": "intake", "conf": 0.98}]
    intake: dict = field(default_factory=dict)       # name -> Value
    stubs: list = field(default_factory=list)        # list of dict name -> Value, plus "page"
    bank: dict = field(default_factory=dict)
    benefit: dict = field(default_factory=dict)
    tradelines: list = field(default_factory=list)
    letters: list = field(default_factory=list)
    seconds: float = 0.0
    ocr: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Extractor:
    name = "base"

    def extract(self, file_id: str, packet) -> FileExtraction:  # packet is ocr.PacketText
        raise NotImplementedError


EXTRACTORS: dict = {}


def register(cls):
    EXTRACTORS[cls.name] = cls
    return cls


def get_extractor(name: str) -> Extractor:
    from . import local  # noqa: F401  registers the local readers
    return EXTRACTORS[name]()
