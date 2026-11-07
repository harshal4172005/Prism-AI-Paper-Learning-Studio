"""A fixed, operator-provided sample; never accepts paths from the browser."""
import os
from pathlib import Path
from app import library

TITLE="Attention Is All You Need"
FILENAME="Attention-Is-All-You-Need.pdf"


def path():
    return Path(os.getenv("PRISM_SAMPLE_PDF",str(library.DATA_ROOT/"samples"/"attention-is-all-you-need.pdf")))
