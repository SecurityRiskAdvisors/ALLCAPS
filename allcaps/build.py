from pathlib import Path
import os
import subprocess
import textwrap

from .enums import Architecture
from .data import GlobalState


def shell(cli: list, env: dict = None, timeout: int = 60, check: bool = True, **kwargs) -> str:
    """
    Shell command handler
    """
    new_env = os.environ.copy()
    if os.getenv("ALLCAPS_SHOW_COMMANDS", None):
        print(subprocess.list2cmdline(cli))
    if env:
        new_env = {**new_env, **env}

    try:
        proc = subprocess.run(
            args=cli,
            check=check,
            env=new_env,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    except subprocess.CalledProcessError as e:
        # print the error indented
        output_raw = e.output.decode()
        output_tabbed = textwrap.indent(output_raw, "\t")
        # this commented out block was for sizing the error
        # based on the terminal size. it didnt work how i wanted
        # but i may come back
        #
        # term_sz = shutil.get_terminal_size((80, 20))
        # output_wrapped = textwrap.wrap(output_tabbed, width=term_sz.columns)
        # output_final = "\n".join(output_wrapped)
        print(f"Process error: \n{output_tabbed}")
        return output_raw
    else:
        return proc.stdout


class GCCWin:
    """
    MinGW-w64 handler
    Requires installation (see https://www.mingw-w64.org/)
    """

    def __init__(self):
        pass

    def compile(self, src: Path, **shell_kwargs):
        """
        Given source file, compile to the destination
        """
        match GlobalState.architecture:
            case Architecture.x64:
                cmd = "x86_64-w64-mingw32-gcc"
            case Architecture.x86:
                cmd = "i686-w64-mingw32-gcc"
            case _:
                raise Exception("Unknown architecture")
        cli = [cmd, src.as_posix(), "-o", GlobalState.outfile.as_posix()]
        if GlobalState.build_options and len(GlobalState.build_options) > 0:
            cli.extend(GlobalState.build_options)
        shell(cli=cli, **shell_kwargs)
