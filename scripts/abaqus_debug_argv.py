# -*- coding: utf-8 -*-
from __future__ import print_function

import codecs
import sys

with codecs.open("outputs/abaqus_debug_argv.txt", "w", "utf-8") as handle:
    handle.write(repr(sys.argv))

print("argv written")
