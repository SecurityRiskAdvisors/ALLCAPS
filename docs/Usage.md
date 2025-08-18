# ALLCAPS Usage

## Requirements

- [Mingw-w64](https://www.mingw-w64.org/) available in your PATH

## Config

ALLCAPs requires a config file detailing the desired capabilities.

The config schema is as follows:

```
outfile: Str!
capabilities: 
    directory: Str!
    desired: Map[]!
exports: Str[]
constraints: Map!
```

`outfile` is the output file path.

`capabilities.directory` is the base directory containing all capabilities.

The `capabilities.desired` key is a list of capabilities and their configurations. The key is the capability name and the value is a map of key-value pairs for that capability as determined by its capability.yml file.

For example, assume you have a capability called `cleareventlog` that exposes one configuration option called `channel`. To include this capability in the config, the `desired` list item would look like:

```
capabilities:
    desired:
    - cleareventlog:
        channel: foo
``` 

The following keys are allowed for the `constraints` section:

- `language`: the source language. This is used in combination with the `capabilities.directory` value to locate capability files. E.g. if `language` = `c` and the capability name is `cleareventlog`, ALLCAPS will search for the `capability.yml` file at `<directory>/c/cleareventlog/capability.yml`.
- `foramt`: the output file format. One of `exe`, `dll`, and `coff`.
- `architecture`: the output file architecture. One of `x64`, `x86`.

The `exports` key is optional. It is used to configure DLL export functions as well as service executables. For DLL exports, each export string should be in one of the following format:

- `<export name>`
- `rundll32::<export name>`. Allows the DLL to be called with `rundll32 <export name>`.
- `regsvr32::<export name>`. The `export name` must be one of `dllregisterserver`, `dllunregisterserver`, `dllinstall`. These exports allow the DLL to be called with `regsvr32 /s`.
- `service::<export name>`. Adds the service main requirements for use as a service DLL. This can also be used when the output type is an exe to allow the exe to act as a service executable.

## CLI options

```
usage: ALLCAPS [-h] [-c CONFIG] [-d] [--override-outfile OUTFILE] [--override-format FORMAT] [--override-architecture ARCHITECTURE] [-i]

options:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
  -d, --cleanup
  --override-outfile OUTFILE
  --override-format FORMAT
  --override-architecture ARCHITECTURE
  -i, --inspect
```

`--override-outfile`, `--override-format`, and `--override-architecture` override the outfile, format, and architecture in the config file, respectively.

`-d` controls whether the temporary files created by the tool are deleted (or not). ALLCAPS creates a temporary working directory to place the generate source code and header file in prior to compilation. Specifying `-d` will delete these files after the payload is compiled.

`-i` can be used to simply inspect the capability requirements of the capabilities in the config. This will print out required template inputs (which should be provided in the config) as well as required runtime input, which should be provided either on the command line (for PEs) or through the COFF interface (for COFFs).

## Environment Variables

The following environment variables can be used to control certain ALLCAPS behaviors:

- `ALLCAPS_SHOW_COMMANDS`: when set will print out the command used to compile the payload. This is useful for debugging purposes.


