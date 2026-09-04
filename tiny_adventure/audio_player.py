"""Playing sound: music, effects, and volume.

The synthesis itself is in audio.py; this file only plays what that produces.

FIRST RUN generates the WAV files. The effects are quick, but the 14-minute
soundtrack takes about 20 seconds, so it is rendered on a background thread
and faded in when ready - the game stays playable meanwhile. Once written to
sounds/theme.wav it is simply reused, so this only happens once.

    Deleting sounds/theme.wav forces the music to be rebuilt.

PLAYBACK uses the Windows MCI interface, which (unlike winsound) can play
several sounds at once and loop the music. On anything other than Windows all
of this quietly does nothing and the game falls back to a terminal bell.

VOLUME is 0-100 here and converted to MCI's 0-1000 scale. Music and effects
are independent, both persist to settings, and the - and + keys adjust music
from anywhere in the game.
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (WEAPONS, FINESSE, ARMOR, CLASSES, DIFFICULTIES, CLASS_SPELLS,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, SPELL_CATALOG)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class AudioMixin:

    def init_sounds(self):
        # keep previously loaded settings if load_settings already ran
        """Set up audio: create the sounds folder, render anything missing, open it.

        The soundtrack is rendered on a background thread if it does not exist yet,
        so a first run is playable immediately rather than freezing.
        
"""
        self.sound_enabled = getattr(self, 'sound_enabled', True)
        self.music_enabled = getattr(self, 'music_enabled', True)
        self.music_volume = getattr(self, 'music_volume', 60)
        self.sfx_volume = getattr(self, 'sfx_volume', 80)
        self.sound_dir = os.path.join(game_dir(), 'sounds')
        self.mci = MciAudio()
        self._music_playing = False
        try:
            os.makedirs(self.sound_dir, exist_ok=True)
            for name, notes in SOUND_DEFS.items():
                path = os.path.join(self.sound_dir, name + '.wav')
                if not os.path.exists(path):
                    write_sound_file(path, notes)
            if self.mci.ok:
                # open every effect once under an alias; mpegvideo devices can
                # overlap each other and support looped playback for the music
                for name in SOUND_DEFS:
                    path = os.path.join(self.sound_dir, name + '.wav')
                    self.mci.cmd(f'open "{path}" type mpegvideo alias sfx_{name}')
                self.apply_sfx_volume()
            music_path = os.path.join(self.sound_dir, 'theme.wav')
            self._bgm_opened = False
            if os.path.exists(music_path):
                self._open_and_start_music(music_path)
            else:
                # the full suite is a quarter of an hour long, so it is rendered
                # in a background thread and faded in once it is ready
                self._music_generated = False
                self._music_progress = (0, MUSIC_MOVEMENTS)

                def generate():
                    def note_progress(done, total):
                        self._music_progress = (done, total)
                    try:
                        write_music_file(music_path, progress=note_progress)
                    except Exception:
                        pass
                    self._music_generated = True

                threading.Thread(target=generate, daemon=True).start()
                self._poll_music(music_path)
        except Exception as e:
            # sounds are optional; the game keeps working without them
            print(f"Could not create sound files: {e}")

    def _poll_music(self, music_path):
        """Check whether the background render has finished, and start the music when it has."""
        if getattr(self, '_music_generated', False) and os.path.exists(music_path):
            self._open_and_start_music(music_path)
            try:
                self.log_message("Your bard finishes tuning: the dungeon theme begins.", color='important')
            except Exception:
                pass
        else:
            # let the player know the long track is still being written
            try:
                done, total = getattr(self, '_music_progress', (0, MUSIC_MOVEMENTS))
                if done and done != getattr(self, '_music_progress_logged', -1):
                    self._music_progress_logged = done
                    self.log_message(f"(Composing the dungeon theme: movement {done} of {total}...)")
            except Exception:
                pass
            try:
                self.root.after(700, lambda: self._poll_music(music_path))
            except Exception:
                pass

    def _open_and_start_music(self, music_path):
        """Open the finished soundtrack and begin playing it on a loop."""
        if getattr(self, 'mci', None) and self.mci.ok:
            self.mci.cmd(f'open "{music_path}" type mpegvideo alias bgm')
            self._bgm_opened = True
        self.apply_music_volume()
        self.start_music()

    def apply_music_volume(self):
        """Push the current music volume to the audio device."""
        if getattr(self, 'mci', None) and self.mci.ok and getattr(self, '_bgm_opened', False):
            self.mci.set_volume('bgm', getattr(self, 'music_volume', 60))

    def apply_sfx_volume(self):
        """Push the current effects volume to every loaded sound."""
        if getattr(self, 'mci', None) and self.mci.ok:
            vol = getattr(self, 'sfx_volume', 80)
            for name in SOUND_DEFS:
                self.mci.set_volume(f'sfx_{name}', vol)

    def set_music_volume(self, percent, log=False):
        """Set music volume (0-100), stopping the track entirely at 0.

        Updates the on-screen slider and saves the setting.
        
"""
        self.music_volume = max(0, min(100, int(round(float(percent)))))
        self.apply_music_volume()
        if self.music_volume == 0:
            self.stop_music()
        elif getattr(self, 'music_enabled', True) and not getattr(self, '_music_playing', False):
            self.start_music()
        if hasattr(self, 'music_volume_label'):
            try:
                self.music_volume_label.configure(text=f"{self.music_volume}%")
            except Exception:
                pass
        if log:
            self.log_message(f"Music volume: {self.music_volume}%.")
        try:
            self.save_settings()
        except Exception:
            pass

    def nudge_music_volume(self, delta):
        """Change music volume by a step - what the - and + keys call."""
        self.set_music_volume(getattr(self, 'music_volume', 60) + delta, log=True)
        if hasattr(self, 'music_scale'):
            try:
                self.music_scale.set(self.music_volume)
            except Exception:
                pass

    def play_sound(self, name):
        """Play a named effect without blocking the game.

        Safe to call from anywhere; does nothing if sound is off or muted.
        
"""
        if not getattr(self, 'sound_enabled', True):
            return
        if getattr(self, 'sfx_volume', 80) <= 0:
            return
        if getattr(self, 'mci', None) and self.mci.ok:
            self.mci.cmd(f'seek sfx_{name} to start')
            self.mci.cmd(f'play sfx_{name}')
            return
        path = os.path.join(getattr(self, 'sound_dir', ''), name + '.wav')
        if winsound is not None and os.path.exists(path):
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass
        else:
            # non-Windows fallback: a simple bell so there's at least feedback
            try:
                self.root.bell()
            except Exception:
                pass

    def start_music(self):
        """Start the soundtrack looping, if music is enabled and audible."""
        if (getattr(self, 'music_enabled', True) and getattr(self, 'music_volume', 60) > 0
                and getattr(self, 'mci', None)
                and self.mci.ok and getattr(self, '_bgm_opened', False)):
            self.mci.cmd('seek bgm to start')
            self.mci.cmd('play bgm repeat')
            self._music_playing = True
            self.apply_music_volume()

    def stop_music(self):
        """Stop the soundtrack."""
        if getattr(self, 'mci', None) and self.mci.ok:
            self.mci.cmd('stop bgm')
        self._music_playing = False
