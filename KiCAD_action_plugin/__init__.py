"""
    Module used for registering action plugin
"""

import os
import sys

from .kc_2_fc_action import Kc2FcAction  # Note the relative import!

# For relative imports to work in Python 3.6
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

Kc2FcAction().register()  # Instantiate and register to Pcbnew