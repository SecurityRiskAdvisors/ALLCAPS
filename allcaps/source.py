from dataclasses import dataclass, field
from tempfile import mkstemp
from typing import Set, List, Optional, TypeVar
from pathlib import Path
from importlib.resources import path as resource_path
import shutil
import jinja2
import uuid
import textwrap

from .utils import gen_rand_dir
from .data import GlobalState
from .enums import (
    BaseExportType,
    OutputFormat,
    ExeExportType,
    ExportType,
    RegSvr32ExportType,
    CaseInsensitiveEnum,
    auto,
)
from .templating import TemplateContainer

BaseExportTypeT = TypeVar("BaseExportTypeT", bound=BaseExportType)


class LocationMain(CaseInsensitiveEnum):
    """
    Location is used to position functions appropriately before/after the main function
    E.g. If the function calls main, it should be post-main
    """

    Pre = auto()
    Main = auto()
    Post = auto()


@dataclass
class Export:
    """
    Wrapper class for user-supplied PE exports
    """

    type: BaseExportTypeT
    name: str

    # below funcs used for compatibility with sets
    def __hash__(self):
        return hash((self.name, self.type.__class__.__name__, self.type.name))

    def __eq__(self, other):
        return self.name == other.name and self.type == other.type


def get_resource_tpl(tpl_name) -> jinja2.Template:
    """
    Get a template by file name from this packages resource directory
    """
    with resource_path("allcaps", "resources") as p:
        templates_path = p / "templates" / f"{tpl_name}.{GlobalState.language.name.lower()}.j2"
        template_str = templates_path.read_text()
        # this seems easier than using a second env filesystem loader
        template = GlobalState.environment.from_string(template_str)
        return template


@dataclass
class CFunction:
    """
    Container for source code functions
    """

    name: str
    body: str

    # function location relative to the main function
    location: LocationMain

    # return type can be a single type or multiple values in serial
    # like a return type + calling convention (e.g. "void __stdcall")
    # the value is simply used as-is before the function name
    return_type: str = "void"
    # list of values to be used in the func sig. should be the type + name (e.g. "int foo")
    options: List[str] = field(default_factory=list)

    # e.g. dllexport/dllimport/extern style modifiers
    modifier: Optional[str] = None

    def render(self) -> str:
        options = ", ".join(self.options)
        modifier = "" if not self.modifier else f"{self.modifier}\n"
        body = textwrap.indent(self.body, prefix="\t")
        return f"""{modifier}{self.return_type} {self.name}({options}){{\n{body}\n}}"""

    # below funcs used for compatibility with sets
    def __hash__(self):
        return hash((self.name, self.__class__.__name__))

    def __eq__(self, other):
        return self.name == other.name and isinstance(other, self.__class__)


def render_fns_by_location(location: LocationMain, functions: Set[CFunction]) -> str:
    rendered = ""
    filtered_functions = list(filter(lambda x: x.location == location, functions))
    for function in filtered_functions:  # type: CFunction
        rendered_fn = function.render()
        rendered += rendered_fn
        rendered += "\n\n"
    return rendered


@dataclass
class CSource:
    """
    Container for entire payload source code
    """

    pre_imports: Set[str] = field(default_factory=set)
    imports: Set[str] = field(default_factory=set)
    post_imports: Set[str] = field(default_factory=set)
    post_main: Set[str] = field(default_factory=set)

    functions: Set[CFunction] = field(default_factory=set)
    exports: Set[Export] = field(default_factory=set)
    templates: List[TemplateContainer] = field(default_factory=list)

    # build_args: Set[str] = field(default_factory=set)

    def add_import(self, import_: str, format_: bool = True):
        if format_:
            import_ = f"#include <{import_}>"
        self.imports.add(import_)

    def render_imports(self) -> str:
        win_import = "#include <windows.h>"
        wchar_import = "#include <wchar.h>"

        # windows.h import needs to be first so pop it here then add
        # back later
        add_win_import = False
        if win_import in self.imports:
            self.imports.remove(win_import)
            add_win_import = True

        if wchar_import in self.imports and GlobalState.format == OutputFormat.Coff:
            # need to add -mno-stack-arg-probe to prevent issues
            # resolving __chkst_ms with COFFs
            # this is seemingly added by MinGW+gcc,
            # still havent tested with Clang
            GlobalState.build_options.add("-mno-stack-arg-probe")

        imports = list(self.imports)
        if add_win_import:
            imports.insert(0, win_import)

        imports_str = "\n".join(imports)
        return imports_str

    def render_premain(self) -> str:
        pre_imports = "\n".join(self.pre_imports)
        post_imports = "\n".join(self.post_imports)
        imports = self.render_imports()
        global_pre_main = "\n".join(GlobalState.pre_main)
        joined = pre_imports + "\n" + imports + "\n" + post_imports + "\n" + global_pre_main
        return joined

    def process_main(self):
        """
        Converts the source templates into functions
        """
        num_args = 0
        sub_function_calls = []

        match GlobalState.format:
            case OutputFormat.Coff:
                main_fn_name = "go"
                main_fn_args = ["char * args", "int arlen"]
                sub_fn_args = ["LPCWSTR argv[]"]
                sub_fn_call_args = "argv"
                arg_offset = 1

            case _:
                main_fn_name = "main"
                main_fn_args = ["int argc", "wchar_t *argv[]"]
                sub_fn_args = ["int argc", "wchar_t *argv[]"]
                sub_fn_call_args = "argc, argv"
                arg_offset = 0

        for container in self.templates:
            """
            for each template, construct a container function then add a call of that
            function to the main function body. e.g.:

            void func_ABC(...){ /* do stuff here */ }
            void func_DEF(...){ /* do stuff here */ }
            void main(...){ func_ABC(); func_DEF(); }

            arg handling gets added to main then propagated to all sub functions
            """

            with GlobalState.environment.template_ctx(container):
                capability_args = container.args if container.args else {}
                rendered_tpl = container.template.render(**capability_args)
            func_id = "fn" + str(uuid.uuid4()).replace("-", "")
            args_section = None
            if (args := GlobalState.environment.arg_mapping.get(container.id, None)) is not None:
                args_section = ""
                for arg in args:
                    # for rundll, need to incremenet the position since the dll name
                    # will be the first arg
                    # TODO: this likely breaks with a space b/w the dll and export
                    #       e.g. "dll,export <args>" is fine but not "dll, export <args>"
                    args_section += f"LPWSTR {arg.name} = argv[{arg.position - arg_offset}];"
                    args_section += "\n"
                    num_args += 1

            sub_func_body = ""
            if args_section:
                sub_func_body += args_section
                sub_func_body += "\n"
            sub_func_body += rendered_tpl
            self.functions.add(
                CFunction(
                    name=func_id, return_type="void", body=sub_func_body, options=sub_fn_args, location=LocationMain.Pre
                )
            )

            sub_function_calls.append(f"{func_id}({sub_fn_call_args});")

        main_func_body = "\n".join(sub_function_calls)

        if GlobalState.format == OutputFormat.Coff:
            coff_arg_handler = get_resource_tpl("coffargs").render(num_args=num_args)
            main_func_body = coff_arg_handler + "\n" + main_func_body
        main_func = CFunction(
            name=main_fn_name, return_type="void", body=main_func_body, options=main_fn_args, location=LocationMain.Main
        )
        self.functions.add(main_func)

    def _process_postmain_dll(self):
        """
        Add DLL-specific features like a DllMain and optional features like DLL exports
        """
        dllmain_body = get_resource_tpl("dllmain").render()
        dllmain_fn = CFunction(
            name="DllMain",
            return_type="BOOL WINAPI",
            options=["HINSTANCE hinstDLL", "DWORD fdwReason", "LPVOID lpReserved"],
            body=dllmain_body,
            location=LocationMain.Post,
        )
        self.functions.add(dllmain_fn)

        wmain = CFunction(
            name="wmain",
            return_type="int",
            options=["int argc", "wchar_t *argv[]"],
            body="main(argc, argv);",
            location=LocationMain.Post,
        )
        self.functions.add(wmain)

        export_func_body = textwrap.dedent(
            """
            LPWSTR *szArglist;
            int nArgs;
            szArglist = CommandLineToArgvW(GetCommandLineW(), &nArgs);
            main(nArgs, szArglist);
            """
        )

        for export in self.exports:
            match export.type:
                case ExportType.Service:
                    svc_name = export.name

                    self.post_imports.add(f'#define SERVICE_NAME L"{svc_name}"')
                    self.post_imports.add(f"SERVICE_STATUS ServiceStatus;")
                    self.post_imports.add(f"SERVICE_STATUS_HANDLE hStatus;")

                    svc_handler = get_resource_tpl("servicehandler").render()
                    self.functions.add(
                        CFunction(
                            name="ControlHandler",
                            return_type="void",
                            options=["DWORD request"],
                            body=svc_handler,
                            location=LocationMain.Post,
                        ),
                    )

                    svc_main = get_resource_tpl("servicemain").render()
                    self.functions.add(
                        CFunction(
                            name="ServiceMain",
                            return_type="void",
                            options=["int argc", "wchar_t* argv[]"],
                            body=svc_main,
                            modifier="__declspec(dllexport)",
                            location=LocationMain.Post,
                        )
                    )

                case ExportType.Rundll32:
                    rundll_fn = CFunction(
                        name=export.name,
                        return_type="void __stdcall",
                        options=["HWND hWnd", "HINSTANCE hInst", "LPSTR lpszCmdLine", "int nCmdShow"],
                        body=export_func_body,
                        modifier="__declspec(dllexport)",
                        location=LocationMain.Post,
                    )
                    self.functions.add(rundll_fn)

                case ExportType.Regsvr32:
                    try:
                        regsvr32_export_type = RegSvr32ExportType(export.name)
                    except KeyError:
                        raise Exception("Invalid RegSvr32 export")

                    args = []
                    if regsvr32_export_type == RegSvr32ExportType.DllInstall:
                        args = ["BOOL bInstall", "PCWSTR pszCmdLine"]

                    func_body = export_func_body + "\nreturn S_OK;"
                    regsvr_fn = CFunction(
                        name=export.name,
                        return_type="HRESULT __stdcall",
                        options=args,
                        body=func_body,
                        modifier="__declspec(dllexport)",
                        location=LocationMain.Post,
                    )
                    self.functions.add(regsvr_fn)

                case _:
                    plain_fn = CFunction(
                        name=export.name,
                        return_type="void",
                        options=[],
                        body=export_func_body,
                        modifier="__declspec(dllexport)",
                        location=LocationMain.Post,
                    )
                    self.functions.add(plain_fn)

    def _process_postmain_exe(self):
        """
        Add Exe-specific features like a wmain and optional features like a service controller
        """
        svc_exports = list(filter(lambda x: x == ExeExportType.Service, self.exports))
        num_exports = len(svc_exports)
        if num_exports == 0:
            wmain_body = "main(argc, argv);"
        else:
            svc_export: Export = svc_exports[0]
            svc_name = svc_export.name

            self.post_imports.add(f'#define SERVICE_NAME L"{svc_name}"')
            self.post_imports.add(f"SERVICE_STATUS ServiceStatus;")
            self.post_imports.add(f"SERVICE_STATUS_HANDLE hStatus;")

            svc_handler = get_resource_tpl("servicehandler").render()
            self.functions.add(
                CFunction(
                    name="ControlHandler",
                    return_type="void",
                    options=["DWORD request"],
                    body=svc_handler,
                    location=LocationMain.Post,
                )
            )

            svc_main = get_resource_tpl("servicemain").render()
            self.functions.add(
                CFunction(
                    name="ServiceMain",
                    return_type="void",
                    options=["int argc", "wchar_t* argv[]"],
                    body=svc_main,
                    location=LocationMain.Post,
                )
            )
            # {% if export_svcmain %}__declspec(dllexport){% endif %}

            wmain_body = get_resource_tpl("serviceexemain").render()

        wmain = CFunction(
            name="wmain",
            return_type="int",
            options=["int argc", "wchar_t *argv[]"],
            body=wmain_body,
            location=LocationMain.Post,
        )
        self.functions.add(wmain)

    def process_postmain(self):
        match GlobalState.format:
            case OutputFormat.Dll:
                self._process_postmain_dll()
            case OutputFormat.Exe:
                self._process_postmain_exe()
            case _:
                pass

    def render_main(self) -> str:
        self.process_postmain()
        self.process_main()

        main = ""
        main += render_fns_by_location(LocationMain.Pre, self.functions)
        main += render_fns_by_location(LocationMain.Main, self.functions)
        main += render_fns_by_location(LocationMain.Post, self.functions)

        return main

    def render(self) -> str:
        main = self.render_main()
        pre_main = self.render_premain()
        return f"""// generated by ALLCAPS\n\n{pre_main}\n\n{main}"""


@dataclass
class CSourceWorkspace:
    """
    Container for source code directory (payload source, headers, etc)
    """

    source: CSource = field(default_factory=CSource)
    directory: Path = field(default_factory=gen_rand_dir)

    def copy_headers_to_dir(self):
        """
        Copy the default headers (e.g. beacon.h) to the build directory
        """
        with resource_path("allcaps", "resources") as p:
            headers_dir = p / "headers"
            for header in headers_dir.glob("*.h"):
                shutil.copy(header, self.directory)
                import_ = f'#include "{header.name}"'
                self.source.add_import(import_, format_=False)

    def __post_init__(self):
        self.copy_headers_to_dir()

    def write_source(self) -> Path:
        """
        Render the final payload source to the project directory
        """
        src_f = Path(mkstemp(suffix=f".{GlobalState.language.lower()}", dir=self.directory)[1])
        rendered = self.source.render()
        src_f.write_text(rendered)
        return src_f
