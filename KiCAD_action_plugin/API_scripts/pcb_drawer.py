"""
    Collection of functions that add new drawings to
"""
import hashlib
import logging

from API_scripts.utils import getDictEntryByKIID, getDrawingByKIID, relativeModelPath, KiCADVector

logger = logging.getLogger("DRAWER")