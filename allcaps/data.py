from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, List, Dict, TypeVar
import jinja2

from .enums import enum_dc_field, SourceLanguage, OutputFormat, Architecture
from .utils import gen_rand_dir


JinjaEnvT = TypeVar("JinjaEnvT", bound=jinja2.Environment)


@dataclass
class WinApiInfo:
    library: str
    preamble: str
    args: List[str] = field(default_factory=list)


WinApiDict = Dict[str, WinApiInfo]


@dataclass
class State:
    """
    Shared state object for working data
    """

    outfile: Path = field(default_factory=lambda: Path("allcaps.out"))
    environment: JinjaEnvT = field(default=None)
    # capabilities: List[Capability] = field(default_factory=list)
    build_options: Set[str] = field(default_factory=set)
    working_dir: Path = field(default_factory=gen_rand_dir)
    language: SourceLanguage = enum_dc_field(SourceLanguage, default=SourceLanguage.C)
    format: OutputFormat = enum_dc_field(OutputFormat, default=OutputFormat.Exe)
    architecture: Architecture = enum_dc_field(Architecture, default=Architecture.x64)
    winapis: WinApiDict = field(default_factory=dict)

    # TODO: revisit
    pre_main: Set[str] = field(default_factory=set)


GlobalState = State()
