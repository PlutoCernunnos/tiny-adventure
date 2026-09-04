"""Tiny Adventure - launcher.

The game itself lives in the tiny_adventure package next to this file; this
just starts it. Keeping the entry point here means the existing .bat and .vbs
launchers and the desktop shortcut carry on working unchanged.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tiny_adventure import main, TinyAdventureGUI

# Re-export the public names that used to live in this file when the whole
# game was mane_game.py, so old scripts and the test harnesses that load this
# module (test_fixes.py, test_dialogs.py) keep working after the package split.
from tiny_adventure.data import *    # CLASSES, CLASS_SPELLS, items, spells...
from tiny_adventure.audio import *   # MciAudio, MUSIC_MOVEMENTS, compose_music...

if __name__ == "__main__":
    main()
