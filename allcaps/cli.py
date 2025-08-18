import argparse
from pathlib import Path
import sys
import shutil

from .coordinator import Coordinator
from .templating import get_template_args
from .loader import UserConfig, Capability
from .data import GlobalState
from .enums import Architecture, OutputFormat


def resolve_str_to_path(path: str) -> Path:
    return Path(path).resolve()


def main():
    parser = argparse.ArgumentParser(prog="ALLCAPS")
    parser.add_argument("-c", "--config")
    parser.add_argument("-d", "--cleanup", action="store_true", default=False)

    # overrides
    parser.add_argument("--override-outfile", dest="outfile", required=False, default=None)
    parser.add_argument("--override-format", dest="format", required=False, default=None)
    parser.add_argument("--override-architecture", dest="architecture", required=False, default=None)

    parser.add_argument("-i", "--inspect", action="store_true", default=False)

    args = parser.parse_args()
    config_path = resolve_str_to_path(args.config)

    if not config_path.is_file():
        print("[x] Error reading config!")

    user_cfg: UserConfig = UserConfig.from_file(config_path)
    # TODO: generalize this to support other config options
    if args.outfile:
        user_cfg.outfile = Path(args.outfile).resolve()
    if args.format:
        user_cfg.constraints.format = OutputFormat(args.format)
    if args.architecture:
        user_cfg.constraints.architecture = Architecture(args.architecture)

    coordinator = Coordinator(user_cfg=user_cfg)

    if args.inspect:
        for template in coordinator.workspace.source.templates:
            capability: Capability = template.capability
            print(f"=== Capability: {capability.name} ({template.template.name}) ===")

            if len(capability.inputs) > 0:
                print("\tTemplate Inputs")
                for k, v in capability.inputs.items():
                    print(f"\t- {k} ({v})")

            cap_args = get_template_args(template.template)
            if len(cap_args) > 0:
                print("\tRuntime Inputs")
                for cap_arg in cap_args:
                    print(f"\t- {cap_arg}")

        sys.exit(0)

    coordinator.render_and_build()
    print(f"Outfile: {GlobalState.outfile.as_posix()}")

    # TODO: should display grouped by template
    display_args_list = []
    for arg_list in GlobalState.environment.arg_mapping.values():
        for arg in arg_list:
            display_args_list.append(arg)
    sorted(display_args_list, key=lambda x: x.position)
    command_line = " ".join([f"<{arg.name}>" for arg in display_args_list]) if len(display_args_list) > 0 else "<none>"
    print("Command line: " + command_line)

    if args.cleanup:
        shutil.rmtree(coordinator.workspace.directory)


if __name__ == "__main__":
    main()
