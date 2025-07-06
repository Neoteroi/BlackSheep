"""
This file is used to specify Python extensions, which are used when using Cython.
Extensions are used only if the current runtime is CPython and only if there is not an
environment variable: `BLACKSHEEP_NO_EXTENSIONS=1`.
The logic is to support PyPy. See:
https://github.com/Neoteroi/BlackSheep/issues/539#issuecomment-2888631226
"""

import os
from setuptools import Extension, setup
import platform

COMPILE_ARGS = ["-O2"]

# Check for environment variable to skip extensions
skip_ext = (os.environ.get("BLACKSHEEP_NO_EXTENSIONS", "0") == "1" or 
           os.environ.get("BLACKSHEEP_BUILD_PURE", "0") == "1")

EXTENSIONS = [
    "url",
    "exceptions", 
    "headers",
    "cookies",
    "contents",
    "messages",
    "scribe",
    "baseapp",
]

def create_extensions():
    """Create extension modules list"""
    extensions = []
    base_path = Path("blacksheep")

    for ext_name in EXTENSIONS:
        c_file = base_path / f"{ext_name}.c"

        # Check if C file exists
        if c_file.exists():
            extension = Extension(
                f"blacksheep.{ext_name}",
                [str(c_file)],
                extra_compile_args=COMPILE_ARGS,
                language="c",
            )
            extensions.append(extension)
        else:
            print(f"Warning: C file not found for {ext_name}, skipping extension")

    return extensions


# Determine whether to compile extensions based on runtime environment
if platform.python_implementation() == "CPython" and not skip_ext:
    ext_modules = create_extensions()
    print(f"Building with {len(ext_modules)} Cython extensions")
else:
    ext_modules = []
    reason = "PyPy runtime" if platform.python_implementation() != "CPython" else "extensions disabled"
    print(f"Building without extensions ({reason})")

setup(ext_modules=ext_modules)