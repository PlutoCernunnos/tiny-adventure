Quick launch instructions

- To run with a console (shows debug messages): double-click `run_game.bat`.
- To run without a console (no visible terminal): double-click `launch_game.vbs`.
- Alternatively try `run_game_pyw.bat` which prefers `pythonw` if available and falls back to `python`.

Notes:
- These assume `python` (or `pythonw`) is on your PATH. If not, open a terminal and run:

```
python "mane game.py"
```

- Place these files in the same folder as `mane game.py` (already done).

Create a Desktop Shortcut:

- Run `create_desktop_shortcut.ps1` to create a `Tiny Adventure.lnk` on your desktop that launches the game.
- To run the PowerShell script: right-click it and choose "Run with PowerShell" (you may need to enable script execution or run from a PowerShell prompt with the appropriate policy).

First Launch Behavior:

- On the very first run the game will automatically open the character creator to guide new players. This is tracked by a small hidden file `.tiny_adventure_first_run` in the game folder.
