"""omniparser tool — PARKED.

This file is intentionally not imported by `tools/__init__.py`. Enable it by
uncommenting the import there once REPLICATE_API_TOKEN is configured.

Runs microsoft/omniparser-v2 on Replicate to detect and label interactive UI
elements in a screenshot."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from pydantic import Field

from .._mcp import mcp

OMNIPARSER_MODEL = (
    "microsoft/omniparser-v2:"
    "49cf3d41b8d3aca1360514e83be4c97131ce8f0d99abfc365526d8384caa88df"
)


@mcp.tool()
def run_omniparser(
    image: Annotated[
        str,
        Field(
            description=(
                "Image to parse. Accepts an http(s) URL, a base64 data URI "
                "(data:image/...;base64,...), or an absolute path to a local "
                "image file (typically a tempfile from `screen_capture`)."
            )
        ),
    ],
) -> str:
    """Run microsoft/omniparser-v2 on Replicate. Returns JSON with the parsed
    image URL and structured element data. Requires REPLICATE_API_TOKEN."""
    if not os.environ.get("REPLICATE_API_TOKEN"):
        raise RuntimeError("REPLICATE_API_TOKEN is not set.")

    import replicate  # imported lazily — only needed when this tool is enabled

    if image.startswith(("http://", "https://", "data:")):
        model_input = {"image": image}
    else:
        model_input = {"image": Path(image).open("rb")}

    output = replicate.run(OMNIPARSER_MODEL, input=model_input)
    return output if isinstance(output, str) else json.dumps(output)
