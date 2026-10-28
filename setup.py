"""
setup.py: Native CMake builder and platform-tagged wheel packager for RoaScan.

Ensures:
  1. When building a wheel from source (or when the target OS native shared library
     is not pre-populated in `roascan/`), CMake automatically compiles the C++17
     native core (`roascan-native/`) in Release mode.
  2. Foreign-platform shared libraries are excluded from the built wheel.
  3. Wheel creation fails explicitly with RuntimeError if the target platform's
     native shared library (`roascan_core.dll`, `libroascan_core.so`, or
     `libroascan_core.dylib`) is missing or empty.
  4. The wheel is tagged as platform-specific (`Root-Is-Purelib: false`, e.g.
     `py3-none-win_amd64`) with files installed directly at the wheel root (`roascan/`).
"""

import glob
import os
import shutil
import subprocess
import sys
from setuptools import Distribution, setup
from setuptools.command.build_py import build_py as _build_py


class BinaryDistribution(Distribution):
    """Mark distribution as containing native platform binaries so files are placed
    directly into platlib (`roascan/...`) with `Root-Is-Purelib: false`.
    """

    def has_ext_modules(self):
        return True


def _expected_native_lib_name() -> str:
    if sys.platform == "win32":
        return "roascan_core.dll"
    if sys.platform == "darwin":
        return "libroascan_core.dylib"
    return "libroascan_core.so"


def _build_native_via_cmake(root_dir: str, lib_name: str) -> str:
    native_src = os.path.join(root_dir, "roascan-native")
    cmake_lists = os.path.join(native_src, "CMakeLists.txt")
    if not os.path.exists(cmake_lists):
        raise RuntimeError(
            f"Cannot compile native core '{lib_name}': {cmake_lists} not found in source tree."
        )

    build_dir = os.path.join(root_dir, "build", "cmake-native")
    os.makedirs(build_dir, exist_ok=True)

    cfg_cmd = ["cmake", "-S", native_src, "-B", build_dir, "-DCMAKE_BUILD_TYPE=Release"]
    bld_cmd = ["cmake", "--build", build_dir, "--config", "Release"]

    try:
        subprocess.check_call(cfg_cmd)
        subprocess.check_call(bld_cmd)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to compile native C++17 core '{lib_name}' via CMake. "
            f"Ensure CMake (>=3.16) and a C++17 compiler are installed. Details: {exc}"
        ) from exc

    matches = glob.glob(os.path.join(build_dir, "**", lib_name), recursive=True)
    if not matches and sys.platform != "win32":
        alt_name = lib_name[3:] if lib_name.startswith("lib") else lib_name
        matches = glob.glob(os.path.join(build_dir, "**", alt_name), recursive=True)

    if not matches:
        raise RuntimeError(
            f"CMake build succeeded, but expected shared library '{lib_name}' was not found under {build_dir}."
        )
    return matches[0]


class NativeBuildPy(_build_py):
    """Custom build_py that compiles roascan-native via CMake if the target OS binary is absent,
    and verifies the native shared library is packaged into the wheel build directory.
    """

    def run(self):
        root_dir = os.path.dirname(os.path.abspath(__file__))
        pkg_dir = os.path.join(root_dir, "roascan")
        lib_name = _expected_native_lib_name()
        pkg_lib_path = os.path.join(pkg_dir, lib_name)

        force_cmake = os.environ.get("ROASCAN_FORCE_CMAKE", "0") == "1"
        if force_cmake or not os.path.exists(pkg_lib_path) or os.path.getsize(pkg_lib_path) == 0:
            built_lib = _build_native_via_cmake(root_dir, lib_name)
            shutil.copy2(built_lib, pkg_lib_path)

        super().run()

        build_pkg_dir = os.path.join(self.build_lib, "roascan")
        os.makedirs(build_pkg_dir, exist_ok=True)
        target_in_build = os.path.join(build_pkg_dir, lib_name)
        if not os.path.exists(target_in_build) and os.path.exists(pkg_lib_path):
            shutil.copy2(pkg_lib_path, target_in_build)

        # Remove any foreign-OS shared libraries from build staging
        for ext in ("*.dll", "*.so", "*.dylib"):
            for candidate in glob.glob(os.path.join(build_pkg_dir, ext)):
                if os.path.basename(candidate) != lib_name:
                    try:
                        os.remove(candidate)
                    except OSError:
                        pass

        if not os.path.exists(target_in_build) or os.path.getsize(target_in_build) == 0:
            raise RuntimeError(
                f"Wheel build aborted: required native library '{lib_name}' is missing from {build_pkg_dir}."
            )


cmdclass = {"build_py": NativeBuildPy}

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

    class PlatformBdistWheel(_bdist_wheel):
        def get_tag(self):
            _, _, plat = super().get_tag()
            return "py3", "none", plat

    cmdclass["bdist_wheel"] = PlatformBdistWheel
except ImportError:
    pass

setup(distclass=BinaryDistribution, cmdclass=cmdclass)
