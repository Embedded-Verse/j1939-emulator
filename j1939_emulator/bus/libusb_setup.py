"""Ensure pyusb can load libusb-1.0 on Windows for gs_usb / candleLight."""

from __future__ import annotations


def ensure_libusb_backend() -> None:
    """Patch usb.backend.libusb1 so gs_usb.GsUsb.scan/find works on Windows.

    Requires: pip install libusb-package
    """
    import libusb_package
    import usb.backend.libusb1 as libusb1

    if getattr(libusb1, "_j1939_libusb_patched", False):
        return

    _orig = libusb1.get_backend

    def _get_backend(find_library=None):
        return _orig(find_library=libusb_package.find_library)

    libusb1.get_backend = _get_backend  # type: ignore[method-assign]
    libusb1._j1939_libusb_patched = True  # type: ignore[attr-defined]
