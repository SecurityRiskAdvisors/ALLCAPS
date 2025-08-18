from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import jinja2
import yaml

from .loader import UserConfig
from .data import GlobalState, WinApiInfo
from .enums import Architecture, OutputFormat, SourceLanguage, ExportType, ExeExportType
from .source import CSourceWorkspace, Export
from .build import GCCWin
from .templating import CapabilitySourceEnv, TemplateContainer


def populate_state_from_usercfg(cfg: UserConfig):
    """
    Update the global state data based on a user-provided config
    """
    GlobalState.outfile = Path(cfg.outfile).resolve()
    GlobalState.architecture = Architecture(cfg.constraints.architecture)
    GlobalState.format = OutputFormat(cfg.constraints.format)
    GlobalState.language = SourceLanguage(cfg.constraints.language)

    loader = jinja2.FileSystemLoader(searchpath=cfg.capabilities.directory)
    GlobalState.environment = CapabilitySourceEnv(loader=loader)

    winapi_path = Path(cfg.capabilities.directory) / cfg.constraints.language / "winapis.yml"
    winapi_str = winapi_path.read_text()
    winapi_yml = yaml.safe_load(winapi_str)
    winapi_dict = {api: WinApiInfo(**info) for api, info in winapi_yml.items()}

    GlobalState.winapis = winapi_dict


@dataclass
class Coordinator:
    """
    Manager for overall payload generation
    """

    workspace: CSourceWorkspace = field(default_factory=CSourceWorkspace)
    builder: GCCWin = field(default_factory=GCCWin)
    user_cfg: Optional[UserConfig] = None

    def process_exports(self):
        """
        Read user-specified exports and convert to appropriate enums as well as add required headers
        Ex: add a service export adds the service header to the project
        """
        export_list = self.user_cfg.capabilities.exports
        svc_exports = 0

        if not export_list:
            return

        for export in export_list:
            export_type = ExportType.Plain
            if "::" in export:
                export_parts = export.split("::")
                if GlobalState.format == OutputFormat.Exe:
                    export_type = ExeExportType(export_parts[0])
                else:
                    export_type = ExportType(export_parts[0])
                export_name = export_parts[1]
            else:
                export_name = export

            match export_type:
                case ExeExportType.Service | ExeExportType.Service:
                    self.workspace.source.add_import("winsvc.h")
                    svc_exports += 1
                case ExportType.Rundll32:
                    self.workspace.source.add_import("shellapi.h")
                case _:
                    pass

            self.workspace.source.exports.add(Export(name=export_name, type=export_type))

        if svc_exports > 1:
            raise Exception("Multiple service executable exports specified. Max 1.")

    def process_capabilities(self):
        """
        Resolve the requested capabilities to jinja templates then add them to the source code manager
        """
        capability_base_dir = Path(self.user_cfg.capabilities.directory).resolve()

        for capability, args in self.user_cfg.resolve_capabilities():
            for import_ in capability.imports:
                self.workspace.source.add_import(import_)
            for preimport in capability.preimports:
                self.workspace.source.pre_imports.add(preimport)

            # jinja template loader needs the relative path
            #   since the base directory is used for the fs loader
            src_path = capability.file_path.parent / f"main.{self.user_cfg.constraints.language}"
            src_path = src_path.relative_to(capability_base_dir)
            template = GlobalState.environment.get_template(src_path.as_posix())

            # Environment.get_template(...) returns the same Template instance
            # for multiple calls. so there is only 1 Template per file
            # instance attributes do not work b/c of this so need a container
            tplctr = TemplateContainer(template=template, args=args, capability=capability)

            self.workspace.source.templates.append(tplctr)

    def add_build_options(self):
        """
        Update compiler options
        """
        GlobalState.build_options.add("-municode")
        match GlobalState.format:
            case OutputFormat.Coff:
                GlobalState.build_options.add("-c")
            case OutputFormat.Dll:
                GlobalState.build_options.add("-shared")
            case _:
                pass

    def __post_init__(self):
        if self.user_cfg:
            populate_state_from_usercfg(self.user_cfg)

        self.process_exports()
        self.process_capabilities()
        self.add_build_options()

    def render_and_build(self):
        """
        Render final payload then compile it
        """
        src = self.workspace.write_source()
        self.builder.compile(src=src)
