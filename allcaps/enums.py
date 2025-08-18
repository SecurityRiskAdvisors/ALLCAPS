from dataclasses import field
from enum import Enum, IntFlag, auto

import desert
import marshmallow_enum


class CaseInsensitiveEnum(Enum):
    """
    enum that allows for case-insensitive member lookup by name
    CaseInsensitiveEnum("key") -> CaseInsensitiveEnum.Key
    """

    @classmethod
    def _missing_(cls, value):
        # see: https://docs.python.org/3/library/enum.html#enum.Enum._missing_
        #   note that the lookup here is by name rather than by value
        for member in cls:
            if member.name.lower() == value.lower():
                return member
        raise KeyError(f"{value} is not a valid enum member")


class OutputFormat(str, CaseInsensitiveEnum):
    Coff = "coff"
    Dll = "dll"
    Exe = "exe"
    # Shellcode = auto()


class Architecture(str, CaseInsensitiveEnum):
    x64 = "x64"
    x86 = "x86"
    # Any = "any"


class SourceLanguage(str, CaseInsensitiveEnum):
    C = "c"


class BaseExportType(str, CaseInsensitiveEnum):
    pass


class ExportType(BaseExportType):
    Plain = "plain"
    Rundll32 = "rundll32"
    Regsvr32 = "regsvr32"
    Service = "service"


class ExeExportType(BaseExportType):
    Plain = "plain"
    Service = "service"


class RegSvr32ExportType(str, CaseInsensitiveEnum):
    DllRegisterServer = "DllRegisterServer"
    DllUnregisterServer = "DllUnregisterServer"
    DllInstall = "DllInstall"


def enum_dc_field(enum_, default=None):
    """Generate a dataclass field for a Enum"""
    return field(
        default=default,
        metadata=desert.metadata(field=marshmallow_enum.EnumField(enum_, load_by=marshmallow_enum.EnumField.VALUE)),
    )


# TODO: intflag user here to support bitwise operations in the future
class ArchitectureRestriction(IntFlag):
    x64: auto()
    x86: auto()
