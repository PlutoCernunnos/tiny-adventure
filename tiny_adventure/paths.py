"""Where the game keeps its files.

Everything used to call os.path.dirname(os.path.abspath(__file__)), which only
worked while the whole game was one file. Now that the code lives in a package,
that would point at the package folder instead of the game folder, so the base
directory is worked out once here and imported everywhere else.
"""
import os
import sys

def game_dir():
    """The folder holding the game, where saves/ and sounds/ are kept.

    Everything must go through this rather than __file__: from inside the package
    __file__ points at the package folder, which would quietly create a second
    saves directory and orphan existing saves.
    
"""
    if getattr(sys, 'frozen', False):          # bundled with PyInstaller etc.
        return os.path.dirname(sys.executable)
    # ../ from this package folder is the folder containing the launcher
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def in_game_dir(*parts):
    """Join a path relative to the game folder."""
    return os.path.join(game_dir(), *parts)
