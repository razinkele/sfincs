"""Environment-level fix for a zlib symbol clash in this conda env (added 2026-09-03).

conda-forge's `orc` 2.0.3 (required by libarrow 15, which hydromt 0.10 pins via
`pyarrow<16`) statically bundles zlib and exports its symbols. When pyarrow is
imported before rasterio (pandas does this implicitly), libz.so.1 is first loaded
inside Arrow's dependency scope, and zlib's *internal* calls (deflate, crc32, ...)
bind to ORC's copy. libtiff then frees a stream allocated by the other zlib and any
deflate-compressed GeoTIFF write aborts with "free(): invalid pointer".

Loading the real libz into the global symbol scope before anything else makes zlib
resolve its own symbols first. Remove this file once the env moves to a newer
Arrow/ORC (orc >= 2.1 no longer exports zlib symbols).
"""
import ctypes as _ctypes, os as _os, sys as _sys

_libz = _os.path.join(_sys.prefix, "lib", "libz.so.1")
if _os.path.exists(_libz):
    try:
        _ctypes.CDLL(_libz, mode=_ctypes.RTLD_GLOBAL)
    except OSError:
        pass
