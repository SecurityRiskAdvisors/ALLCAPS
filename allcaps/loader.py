from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path

from .utils import FileLoaderMixin, fixup_dc_factory_fields


@dataclass
class Capability(FileLoaderMixin):
    """
    Expected a directory structure like the following

    <language>
    \\_ <name>
        \\_ <files>

    where <language> is the programming language (e.g. c, go, etc), <name> is the name of the
    capability, and <files> are the source code file and the capability specification.
    The source code file extension should match the <language> and the file name should be "main".
    """

    name: str
    description: Optional[str] = field(default="")
    imports: Optional[List[str]] = field(default_factory=list)
    preimports: Optional[List[str]] = field(default_factory=list)

    # Mapping of restrictions that apply to the source code. Should be used sparingly.
    # Example:
    #   architecture: Only64bit     <- (assuming "Only64bit" is a restriction)
    # TODO: restrictions
    restrictions: Optional[Dict[str, Any]] = field(default_factory=dict)

    # descriptions of input arguments. not used for generating code
    inputs: Optional[Dict[str, str]] = field(default_factory=dict)

    def __post_init__(self):
        fixup_dc_factory_fields(self)


CapabilityArgs = Dict[str, Any]


@dataclass
class UserConfigCapabilities:
    directory: str
    desired: List[Dict[str, Optional[CapabilityArgs]]]
    exports: Optional[List[str]] = field(default_factory=list)

    def __post_init__(self):
        fixup_dc_factory_fields(self)


@dataclass
class UserConfigConstraints:
    language: str = "c"
    format: str = "exe"
    architecture: str = "x64"


@dataclass
class UserConfig(FileLoaderMixin):
    """
    User input file schema
    """

    outfile: str
    capabilities: UserConfigCapabilities
    constraints: UserConfigConstraints

    def resolve_capabilities(self) -> List[Tuple[Capability, CapabilityArgs]]:
        base_directory = Path(self.capabilities.directory)
        language = self.constraints.language.lower()

        capabilities = []
        for capability_dict in self.capabilities.desired:
            capability_name, capability_args = list(capability_dict.items())[0]
            spec_path = base_directory / language / capability_name / "capability.yml"
            capability: Capability = Capability.from_file(spec_path)

            # check that the provided args from the user config match the required
            # inputs defined by the capability then raise an exception if the user
            # is missing any of the inputs
            missing_inputs = set()
            for cap_input in capability.inputs.keys():
                if cap_input not in capability_args:
                    missing_inputs.add(cap_input)
            if len(missing_inputs) > 0:
                raise Exception("Missing required inputs: " + ", ".join(missing_inputs))

            capabilities.append((capability, capability_args))

        return capabilities
