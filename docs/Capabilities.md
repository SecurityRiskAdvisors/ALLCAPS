# Writing Capabilities

## Conventions

- Use Unicode (*W) versions of Windows APIs and call them explicitly (e.g. MessageBoxW instead of MessageBoxA or MessageBox)
    - ALLCAPS will compile for UNICODE

## Requirements

Capabilities require two (and only 2) files to be present:

- `main.<language>`: The entirety of the source code for the capabiltiy. While this could potentially be any language, ALLCAPS is currently only developed with C in mind.
- `capability.yml`: A YAML document detailing the capability

## Capability YAML

The capability YAML document follows this schema:

```
name: Str!
description: Str
imports: Str[]
preimports: Str[]
inputs: Map
args: Map
```

`name` and `description` are text fields for providing the capability display name and description.

`imports` is a list of headers used by the source code. These headers will be formatted as `#include` statements in the final payload (e.g. `windows.h` will become `#include <windows.h>`).
`preimports` is a list of string values to include before the import statements and is intended for things that must go outside a function like `#define`s. Since this is a YAML doc, you can include multiline strings via a `|`.

`inputs` and `args` are key-value pairs that provide descriptions of template and runtime inputs for the capability. `inputs` are also used to validate that the user config inputs contain all required template inputs prior to template rendering.

## Templating

Source code files for capabilities are treated as Jinja templates and will be rendered prior to inclusion in the final payload. This allows capability developers to make use of any valid Jinja functionality within their source code files. Additionally, ALLCAPS exposes the following template functions:

- `WINAPI`: Should be used to wrap any API call in the source code. This function signals to ALLCAPS that an API call is present and should be mangled to work with the desired output format. For example, API calls need to modified to use Dynamic Function Resolution when the output format is a COFF, otherwise the API will not be resolved properly by the COFF runtime (e.g. the C2 implant). The API wrapped by this function must also be available in the `winapis.yml` file (see below).
- `ARG`: Injects a new argument into the code and handles retrieving it during runtime. The argument is of the type `LPWSTR`. For COFFs, these arguments are retrieved using `BeaconDataParse` and related functions. For PEs, they are retrieved from `argv`. If multiple capabilities each require arguments, the expected input order is based on the order in the user-provided config. ALLCAPS will print the expected command line order during payload generation.
- `PRINT`: Prints the provided variable using the format-specific mechanism. Expects a variable name for a variable of type `LPWSTR`. For COFFs, printing is done using `BeaconPrintF`. For PEs, printing is done using `WriteConsoleW`.

These functions have the following function signatures:

- `WINAPI`: `<str: API name> [<bool: use GPA>] [<str: GPA override>]`
    - `<bool: use GPA>` can optionally be specified to mangle the API call to resolve the API using `GetProcAddress` + `LoadLibraryW` (and also add the `typedef`s).
    - `<str: GPA override>`: when using `GetProcAddress` mode, this value will override the export name used in the call to `GetProcAddress`. This is only required in edge cases where the export name differs from the API name.
- `ARG`: `<str: arg name>`
- `PRINT`: `<str: variable name>`

## winapis.yml

A `winapis.yml` file is required to support the `WINAPI` template function. Any API wrapped by the `WINAPI` function must be present in this file. This file must be located at the root of the language directory within the capabilities directory (e.g. for C, it would be `<capabilities directory/c/winapis.yml`).

The structure of the file is a YAML document where each key is an API name and its value is a mapping of the following fields:

- `library`: the name of the library the API call is found within
- `preamble`: contains the information required for COFF Dynamic Function Resolution. Typically this is a DECLSPEC, return type, and any modifier like `__stdcall`/`__cdecl`.
- `args`: a list of types for the function arguments

### Example: MessageBoxW

This example walks through populating an entry in the `winapis.yml` for the API `MessageBoxW`.

1. Locate the API documentation in Microsoft's docs: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-messageboxw
2. Note the return type: `int`
3. Note the argument types in order: `HWND`, `LPCWSTR`, `LPCWSTR`, `UINT`
4. Note the library/DLL (found in the Requirements section): `User32.lib`/`User32.dll`
   a. If the base values differ, use the based value from the DLL 
5. Note the header (also in the Requirements section): `winuser.h`
6. Locate a copy of the header either online (e.g. GitHub mirrors of the Windows SDK) or locally (e.g. MinGW includes dirctory) then find the API within the header: `WINUSERAPI int WINAPI MessageBoxW(HWND hWnd,LPCWSTR lpText,LPCWSTR lpCaption,UINT uType);`
    a. The values before the API name are the preamble. Typically the first value is some alias for `DECLSPEC_IMPORT` (e.g. `WINUSERAPI`) and the last value is some alias for `__stdcall` (e.g. `WINAPI`).
7. Construct the entry

The entry should look like:

```yaml
MessageBoxW:
  library: User32
  preamble: WINUSERAPI INT WINAPI
  args:
  - HWND
  - LPCWSTR
  - LPCWSTR
  - UINT
```

Resolving the preamble aliases is also acceptable:

```yaml
MessageBoxW:
  library: User32
  preamble: DECLSPEC_IMPORT INT WINAPI
  args:
  - HWND
  - LPCWSTR
  - LPCWSTR
  - UINT
```

## Capability library

Capabilities should be organized in a directory that has the following structure:

```
<source language>
    |_ <capability name>
        |_ capability.yml
        |_ main.<source language>
    |_ winapis.yml
```

(Note: currently on C is supported, so the top-level directory and file extensions should always be `c`).

## Altogether

Using the above example, the final library would look like:

```
directory: c
    |_ directory: messagebox
        |_ capability.yml
        |_ main.c
    |_ winapis.yml
```

`capability.yml` file contents:

```yaml
name: Message Box
imports:
- windows.h
inputs:
  message: "Text to display in message body"
```

`main.c` file contents:

```
{{ WINAPI("MessageBoxW") }}(0, L"{{ message }}", L"title", 0);
```

`winapis.yml` file contents:

```yaml
MessageBoxW:
  library: User32
  preamble: DECLSPEC_IMPORT INT WINAPI
  args:
  - HWND
  - LPCWSTR
  - LPCWSTR
  - UINT
```

To generate an executable using this capability, a config file would look like:

```yaml
outfile: example.exe

capabilities:
  directory: <path to capabilities directory>
  desired:
  - messagebox:
      message: foo

constraints:
  language: c
  format: exe
  architecture: x64
```

