import jinja2
from jinja2.runtime import Context
from jinja2.nodes import Call
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
import contextlib
from uuid import UUID, uuid4
from pathlib import Path

from .enums import OutputFormat
from .data import GlobalState
from .loader import Capability


@dataclass
class TemplateContainer:
    template: jinja2.Template
    args: dict
    capability: Capability
    id: UUID = field(default_factory=uuid4)


def fmt_api_for_dfr(api_name, api_info) -> Tuple[str, str]:
    """
    Given an API name and info, return the API formatted for use with COFF Dynamic Function Resolution
    Ex: MessageBox -> USER32$MessageBox(...)
    """
    dfr_name = f"{api_info.library.upper()}${api_name}"
    args = "(" + ",".join(api_info.args) + ")" if api_info.args and len(api_info.args) > 0 else "()"
    typeline = f"{api_info.preamble} {dfr_name}{args};"
    return typeline, dfr_name


@jinja2.pass_environment
def xform_winapi(env: "CapabilitySourceEnv", value, use_gpa: bool = False, gpa_override: str = None):
    """
    This template function transforms system API calls to their appropriate form based on target output format.
    For Exe/Dlls, the form is unchanged.
    For Coffs, the form is altered to add the requirements for dynamic function resolution (https://hstechdocs.helpsystems.com/manuals/cobaltstrike/current/userguide/content/topics/beacon-object-files_dynamic-func-resolution.htm).
    If "use_gpa" is specified, the API call will be changed to use LoadLibraryW + GetProcAddress to first resolve the API.
    If a "gpa_override" is specified, the value will be used as the export name in the call to GetProcAddress rather than the API name.
    """

    if (api_info := GlobalState.winapis.get(value, None)) is None:
        raise Exception(f"API {value} not in API mapping file")

    api_link = f"-l{api_info.library.lower()}"
    GlobalState.build_options.add(api_link)

    if use_gpa:
        loadlibrary = "LoadLibraryW"
        getprocaddress = "GetProcAddress"
        # in some edge cases the export name differs from the api name
        # ex CreateVssBackupComponentsInternal vs CreateVssBackupComponents
        gpa_target = value if not gpa_override else gpa_override

        if (ll_api_info := GlobalState.winapis.get(loadlibrary, None)) is None:
            raise Exception(f"API {loadlibrary} not in API mapping file")
        if (gpa_api_info := GlobalState.winapis.get(getprocaddress, None)) is None:
            raise Exception(f"API {getprocaddress} not in API mapping file")

        preamble_parts = api_info.preamble.split(" ")
        # return types can be multiple strings (e.g. unsigned foo)
        return_type = " ".join(preamble_parts[1 : len(preamble_parts) - 1])
        fn_type = preamble_parts[-1]
        args = ", ".join(api_info.args)
        typedef = f"typedef {return_type}({fn_type} *{value}F)({args});"
        GlobalState.pre_main.add(typedef)

        if GlobalState.format == OutputFormat.Coff:
            ll_typeline, ll_dfr_name = fmt_api_for_dfr(loadlibrary, ll_api_info)
            gpa_typeline, gpa_dfr_name = fmt_api_for_dfr(getprocaddress, gpa_api_info)
            GlobalState.pre_main.add(ll_typeline)
            GlobalState.pre_main.add(gpa_typeline)

    if api_info:
        if GlobalState.format == OutputFormat.Coff:
            if use_gpa:
                gpa_call = f'{value}F {value} = ({value}F){gpa_dfr_name}({ll_dfr_name}(L"{api_info.library.lower()}.dll"), "{gpa_target}");'
                value = gpa_call + "\n" + value
            else:
                typeline, dfr_name = fmt_api_for_dfr(value, api_info)
                value = dfr_name
                GlobalState.pre_main.add(typeline)

        else:
            if use_gpa:
                gpa_call = f'{value}F {value} = ({value}F){getprocaddress}({loadlibrary}(L"{api_info.library.lower()}.dll"), "{gpa_target}");'
                value = gpa_call + "\n" + value

    else:
        raise Exception(f"API {value} not defined in API list")

    return value


@jinja2.pass_environment
def xform_print(env: "CapabilitySourceEnv", value):
    """
    This template function add a print statement for the supplied variable, which should be
    of type LPCWSTR/LPWSTR.
    For Exe/Dlls, the printing will be done using WriteConsoleW.
    For Coffs, the printing will be done using BeaconPrintf (from beacon.h).
    """
    match GlobalState.format:
        case OutputFormat.Coff:
            """
            If you run into "Invalid access to memory location" errors with RunOF
            when calling BeaconPrintf, try running the COFF again via COFFLoader
            to see if the issue persists. I've run into issues where RunOF will
            produce that error when calling a working COFF. It will complete successfully
            the first time then subsequent calls will produce the exception for prints
            (but the COFF still runs as expected).
            """
            return f'BeaconPrintf(CALLBACK_OUTPUT, "%ls", {value});'
        case OutputFormat.Exe:
            return f"WriteConsoleW(GetStdHandle(STD_OUTPUT_HANDLE), {value}, wcslen({value}), NULL, NULL);"
        case _:
            return ""


@dataclass
class RuntimeArg:
    name: str
    position: int


@jinja2.pass_context
def xform_args(ctx: Context, value: str):
    """
    This template function handles taking runtime arguments from generated payloads.
    The provided value will be turned into a local LPWSTR variable.
    For ExeDlls, the input arguments are taken from the standard argv.
    For Coffs, arguments are taken from a combination of BeaconDataParse + BeaconDataExtract. When generating the arguments for a Coff, supply the values as wide-character strings.
    """

    ctx.environment: "CapabilitySourceEnv"
    ctx.environment.arg_ct += 1
    arg = RuntimeArg(name=value, position=ctx.environment.arg_ct)
    ctx.environment.arg_mapping.setdefault(ctx.environment.active_ctr.id, []).append(arg)
    return ""


# allcaps-specific global functions
CapabilitySourceGlobals = {"WINAPI": xform_winapi, "PRINT": xform_print, "ARG": xform_args}


class CapabilitySourceEnv(jinja2.Environment):
    def __init__(self, **env_kwargs):
        # loader = jinja2.FileSystemLoader(searchpath=base_path)
        # super().__init__(loader=loader, **env_kwargs)
        super().__init__(**env_kwargs)
        # self.filters = {**self.filters, **CapabilitySourceFilters}
        self.globals = {**self.globals, **CapabilitySourceGlobals}
        # self.parent = parent
        self.arg_mapping: Dict[UUID, List[RuntimeArg]] = dict()  # tpl name -> RuntimeArgs[]
        self.arg_ct = 0
        self.active_ctr: TemplateContainer | None = None

    @contextlib.contextmanager
    def template_ctx(self, container: TemplateContainer):
        self.active_ctr = container
        try:
            yield self
        finally:
            self.active_ctr = None


def get_template_args(template: jinja2.Template) -> Set[str]:
    """
    Given a template, extract calls to the ARG template function from the AST
    This can be used to inspect if a Capability requires runtime inputs
    """
    template_str = Path(template.filename).read_text()
    ast = template.environment.parse(template_str)

    args = set()
    for call in ast.find_all(Call):
        if hasattr(call.node, "name"):
            if call.node.name == "ARG":
                value = call.args[0].value
                args.add(value)

    return args
