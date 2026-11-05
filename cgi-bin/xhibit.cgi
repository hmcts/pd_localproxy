#!/usr/bin/python3
# Deployment replaces the interpreter path with the validated host interpreter.
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'python'))
from localproxy import main
main()
