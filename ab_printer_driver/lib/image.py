# -*- coding: utf-8 -*-
"""JPEG/PNG → ESC/POS raster (GS v 0) conversion."""
import io
import struct

from PIL import Image

THERMAL_80MM_MAX_WIDTH = 576       # 80 mm @ 203 dpi
THERMAL_58MM_MAX_WIDTH = 384       # 58 mm @ 203 dpi


def image_to_escpos_raster(image_bytes, max_width=THERMAL_80MM_MAX_WIDTH):
    """Convert image bytes to ESC/POS raster bytes ready for TCP send.

    Pipeline:
      1. Decode via Pillow
      2. Resize to ≤ max_width, preserving aspect
      3. Pad width to multiple of 8 (byte-align rows)
      4. Grayscale → 1-bit threshold @ 128
      5. Pack bits MSB-first
      6. Emit ESC @, GS v 0, raster data, feed 3, full cut
    """
    img = Image.open(io.BytesIO(image_bytes))

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize(
            (max_width, int(img.height * ratio)),
            Image.LANCZOS,
        )

    width = img.width
    if width % 8 != 0:
        new_width = (width // 8 + 1) * 8
        padded = Image.new('L', (new_width, img.height), 255)
        padded.paste(img.convert('L'), (0, 0))
        img = padded
        width = new_width
    else:
        img = img.convert('L')

    pixels = img.load()
    height = img.height
    width_bytes = width // 8

    raster = bytearray()
    for y in range(height):
        for x_byte in range(width_bytes):
            byte_val = 0
            for bit in range(8):
                x = x_byte * 8 + bit
                if pixels[x, y] < 128:
                    byte_val |= (0x80 >> bit)
            raster.append(byte_val)

    cmd = b'\x1b\x40'                                 # ESC @ init
    cmd += b'\x1d\x76\x30\x00'                        # GS v 0 mode 0
    cmd += struct.pack('BBBB',
                       width_bytes & 0xFF, (width_bytes >> 8) & 0xFF,
                       height & 0xFF, (height >> 8) & 0xFF)
    cmd += bytes(raster)
    cmd += b'\x1b\x64\x03'                            # feed 3
    cmd += b'\x1d\x56\x00'                            # full cut
    return cmd
