from __future__ import print_function

import ctypes
from collections import namedtuple
from contextlib import contextmanager
from ctypes import byref, cast, string_at
from functools import partial

from .pydmtxlib_error import PydmtxlibError
from .wrapper import (
    EXTERNAL_DEPENDENCIES,
    DmtxPackOrder,
    DmtxProperty,
    DmtxScheme,
    DmtxSymbolSize,
    DmtxUndefined,
    DmtxVector2,
    c_ubyte_p,
    dmtxDecodeCreate,
    dmtxDecodeDestroy,
    dmtxDecodeMatrixRegion,
    dmtxDecodeSetProp,
    dmtxEncodeCreate,
    dmtxEncodeDataMatrix,
    dmtxEncodeDestroy,
    dmtxEncodeSetProp,
    dmtxImageCreate,
    dmtxImageDestroy,
    dmtxImageGetProp,
    dmtxMatrix3VMultiplyBy,
    dmtxMessageDestroy,
    dmtxRegionDestroy,
    dmtxRegionFindNext,
    dmtxTimeAdd,
    dmtxTimeNow,
)

ENCODING_SCHEME_PREFIX = "DmtxScheme"
ENCODING_SIZE_PREFIX = "DmtxSymbol"

ENCODING_SCHEME_NAMES = sorted(
    n.name[len(ENCODING_SCHEME_PREFIX) :] for n in DmtxScheme
)

# Not sorting encoding size names - would need to use natural sort order;
# the existing order within DmtxSymbolSize is sensible.
ENCODING_SIZE_NAMES = [n.name[len(ENCODING_SIZE_PREFIX) :] for n in DmtxSymbolSize]

# A rectangle
Rect = namedtuple("Rect", "left top width height")
Rect_vertices = namedtuple("Rect_vertices", "P0 P1 P2 P3")

# Results of reading a barcode
Decoded = namedtuple("Decoded", "data rect")

# Results of encoding data to an image
Encoded = namedtuple("Encoded", "width height bpp pixels")

# Crude mapping from bits-per-pixels to values in DmtxPackOrder enum
_PACK_ORDER = {
    8: DmtxPackOrder.DmtxPack8bppK,
    16: DmtxPackOrder.DmtxPack16bppRGB,
    24: DmtxPackOrder.DmtxPack24bppRGB,
    32: DmtxPackOrder.DmtxPack32bppRGBX,
}


@contextmanager
def _image(pixels, width, height, pack):
    """A context manager for `DmtxImage`, created and destroyed by
    `dmtxImageCreate` and `dmtxImageDestroy`.

    Args:
        pixels (:obj:):
        width (int):
        height (int):
        pack (int):

    Yields:
        DmtxImage: The created image

    Raises:
        PydmtxlibError: If the image could not be created.
    """
    image = dmtxImageCreate(pixels, width, height, pack)
    if not image:
        raise PydmtxlibError("Could not create image")
    else:
        try:
            yield image
        finally:
            dmtxImageDestroy(byref(image))


@contextmanager
def _decoder(image, shrink):
    """A context manager for `DmtxDecode`, created and destroyed by
    `dmtxDecodeCreate` and `dmtxDecodeDestroy`.

    Args:
        image (POINTER(DmtxImage)):
        shrink (int):

    Yields:
        POINTER(DmtxDecode): The created decoder

    Raises:
        PydmtxlibError: If the decoder could not be created.
    """
    decoder = dmtxDecodeCreate(image, shrink)
    if not decoder:
        raise PydmtxlibError("Could not create decoder")
    else:
        try:
            yield decoder
        finally:
            dmtxDecodeDestroy(byref(decoder))


@contextmanager
def _region(decoder, timeout):
    """A context manager for `DmtxRegion`, created and destroyed by
    `dmtxRegionFindNext` and `dmtxRegionDestroy`.

    Args:
        decoder (POINTER(DmtxDecode)):
        timeout (int or None):

    Yields:
        DmtxRegion: The next region or None, if all regions have been found.
    """
    region = dmtxRegionFindNext(decoder, timeout)
    try:
        yield region
    finally:
        if region:
            dmtxRegionDestroy(byref(region))


@contextmanager
def _decoded_matrix_region(decoder, region, corrections):
    """A context manager for `DmtxMessage`, created and destroyed by
    `dmtxDecodeMatrixRegion` and `dmtxMessageDestroy`.

    Args:
        decoder (POINTER(DmtxDecode)):
        region (POINTER(DmtxRegion)):
        corrections (int):

    Yields:
        DmtxMessage: The message.
    """
    message = dmtxDecodeMatrixRegion(decoder, region, corrections)
    try:
        yield message
    finally:
        if message:
            dmtxMessageDestroy(byref(message))


def _decode_region(decoder, region, corrections, shrink, return_vertices=False):
    """Decodes and returns the value in a region.

    Args:
        region (DmtxRegion):

    Yields:
        Decoded or None: The decoded value.
    """
    with _decoded_matrix_region(decoder, region, corrections) as msg:
        if msg:
            # Coordinates
            p00 = DmtxVector2()
            p11 = DmtxVector2(1.0, 1.0)
            p10 = DmtxVector2(1.0, 0.0)
            p01 = DmtxVector2(0.0, 1.0)
            dmtxMatrix3VMultiplyBy(p00, region.contents.fit2raw)
            dmtxMatrix3VMultiplyBy(p11, region.contents.fit2raw)
            dmtxMatrix3VMultiplyBy(p01, region.contents.fit2raw)
            dmtxMatrix3VMultiplyBy(p10, region.contents.fit2raw)
            x00 = int((shrink * p00.X) + 0.5)
            y00 = int((shrink * p00.Y) + 0.5)
            x11 = int((shrink * p11.X) + 0.5)
            y11 = int((shrink * p11.Y) + 0.5)
            x10 = int((shrink * p10.X) + 0.5)
            y10 = int((shrink * p10.Y) + 0.5)
            x01 = int((shrink * p01.X) + 0.5)
            y01 = int((shrink * p01.Y) + 0.5)

            if return_vertices:
                return Decoded(
                    string_at(msg.contents.output),
                    Rect_vertices((x00, y00), (x01, y01), (x10, y10), (x11, y11)),
                )
            else:
                min_x = min(x00, x11, x10, x01)
                max_x = max(x00, x11, x10, x01)
                min_y = min(y00, y11, y10, y01)
                max_y = max(y00, y11, y10, y01)

                return Decoded(
                    string_at(msg.contents.output),
                    Rect(min_x, min_y, max_x - min_x, max_y - min_y),
                )

        else:
            return None


def _pixel_data(image):
    """Returns (pixels, width, height, bpp)

    Returns:
        :obj: `tuple` (pixels, width, height, bpp)
    """
    # Test for PIL.Image, numpy.ndarray, and imageio.core.util without
    # requiring that cv2, PIL, or imageio are installed.

    image_type = str(type(image))
    if "PIL." in image_type:
        pixels = image.tobytes()
        width, height = image.size
    elif "numpy.ndarray" in image_type or "imageio.core.util" in image_type:
        # Different versions of imageio use a subclass of numpy.ndarray
        # called either imageio.core.util.Image or imageio.core.util.Array.
        if "uint8" != str(image.dtype):
            image = image.astype("uint8")
        try:
            pixels = image.tobytes()
        except AttributeError:
            # `numpy.ndarray.tobytes()` introduced in `numpy` 1.9.0 - use the
            # older `tostring` method.
            pixels = image.tostring()
        height, width = image.shape[:2]
    else:
        # image should be a tuple (pixels, width, height)
        pixels, width, height = image

        # Check dimensions
        if 0 != len(pixels) % (width * height):
            raise PydmtxlibError(
                f"Inconsistent dimensions: image data of {len(pixels)} bytes is not "
                f"divisible by (width x height = {width * height})"
            )

    # Compute bits-per-pixel
    bpp = 8 * len(pixels) // (width * height)
    if bpp not in _PACK_ORDER:
        raise PydmtxlibError(
            f"Unsupported bits-per-pixel: [{bpp}]. Should be one of {sorted(_PACK_ORDER.keys())}"
        )
    return pixels, width, height, bpp


def decode(
    image,
    timeout=None,
    gap_size=None,
    shrink=1,
    shape=None,
    deviation=None,
    threshold=None,
    min_edge=None,
    max_edge=None,
    corrections=None,
    max_count=None,
    return_vertices=False,
):
    """Decodes datamatrix barcodes in `image`.

    Args:
        image: `numpy.ndarray`, `PIL.Image` or tuple (pixels, width, height)
        timeout (int): milliseconds
        gap_size (int):
        shrink (int):
        shape (int):
        deviation (int):
        threshold (int):
        min_edge (int):
        max_edge (int):
        corrections (int):
        max_count (int): stop after reading this many barcodes. `None` to read
            as many as possible.
        return_vertices: If to return the coordinates of the four vertices of the datamatrix or just one + width/height

    Returns:
        :obj:`list` of :obj:`Decoded`: The values decoded from barcodes.
    """
    dmtx_timeout = None
    if timeout:
        now = dmtxTimeNow()
        dmtx_timeout = dmtxTimeAdd(now, timeout)

    if max_count is not None and max_count < 1:
        raise ValueError(f"Invalid max_count [{max_count}]")

    pixels, width, height, bpp = _pixel_data(image)

    results = []
    with _image(cast(pixels, c_ubyte_p), width, height, _PACK_ORDER[bpp]) as img:
        with _decoder(img, shrink) as decoder:
            properties = [
                (DmtxProperty.DmtxPropScanGap, gap_size),
                (DmtxProperty.DmtxPropSymbolSize, shape),
                (DmtxProperty.DmtxPropSquareDevn, deviation),
                (DmtxProperty.DmtxPropEdgeThresh, threshold),
                (DmtxProperty.DmtxPropEdgeMin, min_edge),
                (DmtxProperty.DmtxPropEdgeMax, max_edge),
            ]

            # Set only those properties with a non-None value
            for prop, value in ((p, v) for p, v in properties if v is not None):
                dmtxDecodeSetProp(decoder, prop, value)

            if not corrections:
                corrections = DmtxUndefined

            while True:
                with _region(decoder, dmtx_timeout) as region:
                    # Finished file or ran out of time before finding another
                    # region
                    if not region:
                        break
                    else:
                        # Decoded
                        res = _decode_region(
                            decoder, region, corrections, shrink, return_vertices
                        )
                        if res:
                            results.append(res)

                            # Stop if we've reached maximum count
                            if max_count and len(results) == max_count:
                                break

    return results


@contextmanager
def _encoder():
    encoder = dmtxEncodeCreate()
    if not encoder:
        raise PydmtxlibError("Could not create encoder")

    try:
        yield encoder
    finally:
        dmtxEncodeDestroy(byref(encoder))


def encode(data, scheme=None, size=None):
    """
    Encodes `data` in a DataMatrix image.

    For now bpp is the libdmtx default which is 24

    Args:
        data: bytes instance
        scheme: encoding scheme - one of `ENCODING_SCHEME_NAMES`, or `None`.
            If `None`, defaults to 'Ascii'.
        size: image dimensions - one of `ENCODING_SIZE_NAMES`, or `None`.
            If `None`, defaults to 'ShapeAuto'.

    Returns:
        Encoded: with properties `(width, height, bpp, pixels)`.
        You can use that result to build a PIL image:

            Image.frombytes('RGB', (width, height), pixels)

    """

    size = size if size else "ShapeAuto"
    size_name = f"{ENCODING_SIZE_PREFIX}{size}"
    if not hasattr(DmtxSymbolSize, size_name):
        raise PydmtxlibError(
            f"Invalid size [{size}]: should be one of {ENCODING_SIZE_NAMES}"
        )
    size = getattr(DmtxSymbolSize, size_name)

    scheme = scheme if scheme else "Ascii"
    scheme_name = "{0}{1}".format(ENCODING_SCHEME_PREFIX, scheme.capitalize())
    if not hasattr(DmtxScheme, scheme_name):
        raise PydmtxlibError(
            f"Invalid scheme [{scheme}]: should be one of {ENCODING_SCHEME_NAMES}"
        )
    scheme = getattr(DmtxScheme, scheme_name)

    with _encoder() as encoder:
        dmtxEncodeSetProp(encoder, DmtxProperty.DmtxPropScheme, scheme)
        dmtxEncodeSetProp(encoder, DmtxProperty.DmtxPropSizeRequest, size)

        if dmtxEncodeDataMatrix(encoder, len(data), cast(data, c_ubyte_p)) == 0:
            raise PydmtxlibError(
                "Could not encode data, possibly because the image is not "
                "large enough to contain the data"
            )

        w, h, bpp = map(
            partial(dmtxImageGetProp, encoder[0].image),
            (
                DmtxProperty.DmtxPropWidth,
                DmtxProperty.DmtxPropHeight,
                DmtxProperty.DmtxPropBitsPerPixel,
            ),
        )
        size = w * h * bpp // 8
        pixels = cast(encoder[0].image[0].pxl, ctypes.POINTER(ctypes.c_ubyte * size))

        return Encoded(
            width=w,
            height=h,
            bpp=bpp,
            pixels=ctypes.string_at(pixels, size),
        )


__all__ = [
    "decode",
    "encode",
    "Encoded",
    "ENCODING_SCHEME_NAMES",
    "ENCODING_SIZE_NAMES",
    "EXTERNAL_DEPENDENCIES",
]
