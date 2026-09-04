"""The narrator: a small spoken voice for the moments that matter.

The log is the game's real storyteller; this just says the headlines out loud
so you do not have to read every line mid-fight. It is deliberately terse and
deliberately picky about what it speaks:

    - one damage summary per round ("You took 8 damage. 21 health left."),
      never a line per hit
    - kills ("Goblin down."), and "Victory!" when the room is cleared
    - a boss winding up its big move ("Big attack coming. Take cover!")
    - level ups, your companion going down, and your own death

NO NEW DEPENDENCIES. Speech comes from whatever the operating system already
has:

    Windows   the built-in SAPI voice, driven through a single persistent
              PowerShell worker (System.Speech). Started lazily on the first
              phrase, hidden window, exits by itself when the game closes.
    macOS     the `say` command.
    Linux     `espeak`, if installed. Otherwise the narrator silently does
              nothing - the game is identical without it.

HOW IT STAYS NOT-ANNOYING
    - phrases go into a queue of TWO. If the fight talks faster than the
      voice, older phrases are dropped, not stacked - the voice never lags
      three rounds behind the action.
    - a background thread feeds the voice one phrase at a time and waits for
      it to finish, so phrases never talk over each other.
    - it obeys two switches: its own Narrator toggle in Settings, and the
      master Enable Sound Effects switch. All the test harnesses set
      sound_enabled = False, so headless runs never spawn a voice.

The worker thread never touches tkinter, and nothing here blocks the UI.
"""
import os
import queue
import re
import shutil
import subprocess
import sys
import threading

# The persistent Windows worker: reads a line, speaks it, answers 'k' so the
# feeder thread knows it may send the next. ReadLine() returning null (the
# game exited, closing the pipe) ends the loop, so it can never outlive us.
_PS_WORKER = (
    "$ErrorActionPreference='SilentlyContinue';"
    "Add-Type -AssemblyName System.Speech;"
    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$s.Rate=1;"
    "while($true){$l=[Console]::In.ReadLine();"
    "if($l -eq $null){break};"
    "try{$s.Speak($l)}catch{};"
    "[Console]::Out.WriteLine('k');[Console]::Out.Flush()}"
)


class NarratorMixin:

    # ------------------------------------------------------------ speaking

    def narrate(self, text):
        """Queue one short phrase for the voice. Safe to call from anywhere.

        Does nothing at all when the narrator is off, sound is off, or the
        platform has no voice - so callers never need to check first.
        """
        if not getattr(self, 'narrator_enabled', True):
            return
        if not getattr(self, 'sound_enabled', True):
            return
        if self._narrator_backend() is None:
            return
        # keep phrases plain ASCII and short: dodges console codepage trouble
        # on Windows and keeps the voice snappy
        text = re.sub(r'[^\x20-\x7e]', ' ', str(text))
        text = re.sub(r'\s+', ' ', text).strip()[:140]
        if not text:
            return
        self._narrator_ensure_worker()
        q = self._narr_queue
        try:
            q.put_nowait(text)
        except queue.Full:
            # the voice is behind: drop the OLDEST phrase, keep the newest
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(text)
            except queue.Full:
                pass

    def stop_narrator(self):
        """Shut the voice down. Optional - it also dies with the process."""
        proc = getattr(self, '_narr_proc', None)
        self._narr_proc = None
        if proc is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------ plumbing

    def _narrator_backend(self):
        """Which voice this machine has: 'sapi', 'say', 'espeak', or None."""
        cached = getattr(self, '_narr_backend', '?')
        if cached != '?':
            return cached
        backend = None
        try:
            if os.name == 'nt' and shutil.which('powershell'):
                backend = 'sapi'
            elif sys.platform == 'darwin' and shutil.which('say'):
                backend = 'say'
            elif shutil.which('espeak'):
                backend = 'espeak'
        except Exception:
            backend = None
        self._narr_backend = backend
        return backend

    def _narrator_ensure_worker(self):
        """Start the feeder thread on the first phrase (lazily, once)."""
        if getattr(self, '_narr_queue', None) is None:
            self._narr_queue = queue.Queue(maxsize=2)
        thread = getattr(self, '_narr_thread', None)
        if thread is None or not thread.is_alive():
            self._narr_thread = threading.Thread(
                target=self._narrator_worker_loop, name='narrator', daemon=True)
            self._narr_thread.start()

    def _narrator_worker_loop(self):
        """Feed the voice one phrase at a time; three failures and it stops."""
        failures = 0
        while failures < 3:
            try:
                text = self._narr_queue.get()
            except Exception:
                return
            if text is None:
                return
            try:
                self._narrator_speak(text)
                failures = 0
            except Exception:
                failures += 1
        # give up quietly: no voice is better than a crashing one
        self._narr_backend = None

    def _narrator_speak(self, text):
        """Speak one phrase, blocking (in the worker thread) until it is done."""
        backend = self._narrator_backend()
        if backend == 'sapi':
            proc = getattr(self, '_narr_proc', None)
            if proc is None or proc.poll() is not None:
                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                proc = subprocess.Popen(
                    ['powershell', '-NoProfile', '-NonInteractive', '-Command', _PS_WORKER],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, creationflags=flags)
                self._narr_proc = proc
            try:
                proc.stdin.write(text + '\n')
                proc.stdin.flush()
                proc.stdout.readline()   # the worker answers 'k' when done
            except Exception:
                self._narr_proc = None   # broken pipe: rebuild on the next phrase
                raise
        elif backend == 'say':
            subprocess.run(['say', text], check=False)
        elif backend == 'espeak':
            subprocess.run(['espeak', '-s', '170', text],
                           check=False, stderr=subprocess.DEVNULL)
