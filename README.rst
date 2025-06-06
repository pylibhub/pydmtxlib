Pydmtxlib
=========

Forked from `pylibdmtx <https://github.com/NaturalHistoryMuseum/pylibdmtx>`_

Read and write Data Matrix in Python 3.8+ using the
`libdmtx <http://libdmtx.sourceforge.net/>`_ library.

----

Features
--------

- Pure Python interface for ``libdmtx``
- Supports PIL/Pillow images, OpenCV/numpy arrays, and raw bytes
- Decodes barcode data and locations
- Minimal dependencies (only ``libdmtx`` native library required)

Installation
------------

macOS
^^^^^

.. code-block:: bash

    brew install libdmtx gettext

Linux (Ubuntu/Debian)
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    sudo apt-get install libdmtx0t64

Windows
^^^^^^^

Windows Python wheels **do not include** the required ``libdmtx`` DLLs.
You need to download and add the DLLs manually to your system PATH or your project folder.

Python package
^^^^^^^^^^^^^^

.. code-block:: bash

    pip install pydmtxlib

Usage example
-------------

Here is a simple example demonstrating how to **encode** a string into a Data Matrix barcode
and save it as an image, then **decode** it back:

.. code-block:: python

    from PIL import Image
    from pydmtxlib import encode, decode

    # Data to encode must be bytes
    data = b"Hello, Data Matrix!"

    # Encode the data
    encoded = encode(data)

    # Build a PIL image from raw pixels returned by encode()
    image = Image.frombytes('RGB', (encoded.width, encoded.height), encoded.pixels)

    # Save the image
    image.save("datamatrix.png")
    print("Data Matrix saved as 'datamatrix.png'")

    # Open the saved image and decode
    image = Image.open("datamatrix.png")
    results = decode(image)

    # Print decoded results
    for result in results:
        print("Decoded data:", result.data.decode("utf-8"))

