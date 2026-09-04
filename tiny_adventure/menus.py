"""The main menu and the settings dialog.

The main menu is the first thing shown: New Game, Quick Start, Continue, plus
save and load. Settings covers sound, volume, difficulty, autosave and where
saves are kept; everything there is written to settings.json and survives
restarts.

To add a setting: add a widget in open_settings, store it in apply_settings,
and add it to save_settings/load_settings in persistence.py so it persists.
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (WEAPONS, FINESSE, ARMOR, CLASSES, SUBCLASSES, DIFFICULTIES, CLASS_SPELLS,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, SPELL_CATALOG, MAX_START_LEVEL)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class MenuMixin:

    def open_main_menu(self):
        # Modal main menu offering New Game, Quick Start, Continue, Help, Exit
        """The main menu: new game, quick start, continue, save and load."""
        menu = self.make_popup("Main Menu")
        frm = ttk.Frame(menu, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Tiny Adventure", style='Title.TLabel').pack(pady=(0, 2))
        ttk.Label(frm, text="A tiny D&D-inspired sandbox. Start a new game or Quick Start.",
                  style='Dim.TLabel').pack(pady=(0, 10))

        def new_game():
            menu.destroy()
            self.start_game()

        def cont():
            # close menu and continue if character exists
            if not getattr(self, 'character_created', False):
                self.log_message("No character to continue. Create one or Quick Start.")
                return
            menu.destroy()

        ttk.Button(frm, text="New Game (Create Character)", command=new_game).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(frm, text="Continue", command=cont).pack(fill=tk.X, pady=(0, 4))

        # one Quick Start row: class, level, go
        qs = ttk.LabelFrame(frm, text="Quick Start", padding=8)
        qs.pack(fill=tk.X, pady=(6, 4))
        qs_row = ttk.Frame(qs)
        qs_row.pack(fill=tk.X)
        ttk.Label(qs_row, text="Class:").pack(side=tk.LEFT)
        qs_class = ttk.Combobox(qs_row, values=list(CLASSES.keys()), state="readonly", width=12)
        qs_class.set("Fighter")
        qs_class.pack(side=tk.LEFT, padx=(6, 8))
        ttk.Label(qs_row, text="Level:").pack(side=tk.LEFT)
        qs_level = ttk.Spinbox(qs_row, from_=1, to=MAX_START_LEVEL, width=4)
        qs_level.set(1)
        qs_level.pack(side=tk.LEFT, padx=(4, 8))

        qs_row2 = ttk.Frame(qs)
        qs_row2.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(qs_row2, text="Path:").pack(side=tk.LEFT)
        qs_path = ttk.Combobox(qs_row2, state="readonly", width=22)
        qs_path.pack(side=tk.LEFT, padx=(11, 8))

        def refresh_qs_paths(event=None):
            names = ['(random)'] + list(SUBCLASSES.get(qs_class.get() or 'Fighter', {}))
            qs_path.configure(values=names)
            qs_path.set('(random)')

        qs_class.bind('<<ComboboxSelected>>', refresh_qs_paths)
        refresh_qs_paths()

        def quick_start_pick():
            try:
                lvl = max(1, min(MAX_START_LEVEL, int(qs_level.get())))
            except Exception:
                lvl = 1
            cls = qs_class.get() or 'Fighter'
            sub = qs_path.get()
            if sub == '(random)':
                sub = None
            menu.destroy()
            self.quick_start_class(cls, level=lvl, subclass=sub)

        ttk.Button(qs_row2, text="Go!", command=quick_start_pick).pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Save/load controls
        ttk.Separator(frm, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(8, 8))

        def do_save():
            # Save As dialog
            if not getattr(self, 'character_created', False):
                messagebox.showinfo("Save", "No character to save. Create one first.")
                return
            path = filedialog.asksaveasfilename(title="Save Game As", defaultextension='.json', filetypes=[('JSON', '*.json')], initialdir=self.save_folder)
            if path:
                try:
                    self.save_game(path)
                    messagebox.showinfo("Save", f"Saved to {path}")
                except Exception as e:
                    messagebox.showerror("Save Error", str(e))

        def do_load():
            path = filedialog.askopenfilename(title="Load Game", defaultextension='.json', filetypes=[('JSON', '*.json')], initialdir=self.save_folder)
            if path:
                try:
                    self.load_game(path)
                    menu.destroy()
                except Exception as e:
                    messagebox.showerror("Load Error", str(e))

        def do_quicksave():
            try:
                self.save_quick(self.quick_save_path)
                messagebox.showinfo("Quick Save", f"Quick saved to {self.quick_save_path}")
            except Exception as e:
                messagebox.showerror("Quick Save Error", str(e))

        def do_quickload():
            try:
                self.load_game(self.quick_save_path)
                menu.destroy()
            except Exception as e:
                messagebox.showerror("Quick Load Error", str(e))

        sf = ttk.Frame(frm)
        sf.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(sf, text="Save As...", command=do_save).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        ttk.Button(sf, text="Load...", command=do_load).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        sf2 = ttk.Frame(frm)
        sf2.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(sf2, text="Quick Save", command=do_quicksave).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        ttk.Button(sf2, text="Quick Load", command=do_quickload).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)

        def toggle_autosave():
            self.autosave_enabled = not self.autosave_enabled
            if self.autosave_enabled:
                self.start_autosave()
            else:
                self.stop_autosave()
            messagebox.showinfo("AutoSave", f"AutoSave {'enabled' if self.autosave_enabled else 'disabled'}")

        ttk.Button(frm, text="Toggle AutoSave", command=toggle_autosave).pack(fill=tk.X, pady=(2, 4))

        ttk.Separator(frm, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(6, 8))
        ttk.Button(frm, text="Help / Controls", command=self.show_help).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(frm, text="Settings", command=self.open_settings).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(frm, text="Exit", command=self.root.destroy).pack(fill=tk.X, pady=(8, 0))

        self.place_window(menu, min_w=440, min_h=420)

    def open_settings(self):
        """The settings dialog: sound, volume, difficulty, autosave, save folder.

        Volume sliders take effect as you drag them; the rest applies on Apply.
        
"""
        win = self.make_popup("Settings")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # Autosave enable
        autosave_var = tk.BooleanVar(value=getattr(self, 'autosave_enabled', True))
        ttk.Checkbutton(frm, text="Enable AutoSave", variable=autosave_var).pack(anchor=tk.W, pady=(2,4))

        # Sound effects enable
        sound_var = tk.BooleanVar(value=getattr(self, 'sound_enabled', True))
        ttk.Checkbutton(frm, text="Enable Sound Effects", variable=sound_var).pack(anchor=tk.W, pady=(2,4))

        # Background music enable
        music_var = tk.BooleanVar(value=getattr(self, 'music_enabled', True))
        ttk.Checkbutton(frm, text="Enable Background Music", variable=music_var).pack(anchor=tk.W, pady=(2,4))

        # Volume sliders (these take effect as you drag them)
        vol_frame = ttk.LabelFrame(frm, text="Volume", padding=8)
        vol_frame.pack(fill=tk.X, pady=(4, 6))

        music_vol_row = ttk.Frame(vol_frame)
        music_vol_row.pack(fill=tk.X, pady=(2, 2))
        ttk.Label(music_vol_row, text="Music", width=7).pack(side=tk.LEFT)
        music_vol_read = ttk.Label(music_vol_row, text=f"{getattr(self, 'music_volume', 60)}%", width=5)
        music_vol_scale = ttk.Scale(music_vol_row, from_=0, to=100, orient=tk.HORIZONTAL, length=170)
        music_vol_scale.set(getattr(self, 'music_volume', 60))
        music_vol_scale.configure(command=lambda v: (
            self.set_music_volume(float(v)),
            music_vol_read.configure(text=f"{int(float(v))}%"),
            hasattr(self, 'music_scale') and self.music_scale.set(float(v))))
        music_vol_scale.pack(side=tk.LEFT, padx=(4, 6))
        music_vol_read.pack(side=tk.LEFT)

        sfx_vol_row = ttk.Frame(vol_frame)
        sfx_vol_row.pack(fill=tk.X, pady=(2, 2))
        ttk.Label(sfx_vol_row, text="Effects", width=7).pack(side=tk.LEFT)
        sfx_vol_read = ttk.Label(sfx_vol_row, text=f"{getattr(self, 'sfx_volume', 80)}%", width=5)
        sfx_vol_scale = ttk.Scale(sfx_vol_row, from_=0, to=100, orient=tk.HORIZONTAL, length=170)
        sfx_vol_scale.set(getattr(self, 'sfx_volume', 80))

        def set_sfx(v):
            self.sfx_volume = max(0, min(100, int(float(v))))
            self.apply_sfx_volume()
            sfx_vol_read.configure(text=f"{self.sfx_volume}%")
        sfx_vol_scale.configure(command=set_sfx)
        sfx_vol_scale.pack(side=tk.LEFT, padx=(4, 6))
        sfx_vol_read.pack(side=tk.LEFT)
        ttk.Label(vol_frame, text="Tip: the - and + keys change music volume at any time.",
                  style='Dim.TLabel').pack(anchor=tk.W, pady=(4, 0))

        # Log speed: pause between log lines when several arrive at once,
        # so combat rounds read like a story instead of appearing all at once
        log_frame = ttk.LabelFrame(frm, text="Log speed", padding=8)
        log_frame.pack(fill=tk.X, pady=(4, 6))
        log_row = ttk.Frame(log_frame)
        log_row.pack(fill=tk.X, pady=(2, 2))
        ttk.Label(log_row, text="Delay", width=7).pack(side=tk.LEFT)
        log_delay_read = ttk.Label(log_row, text=f"{getattr(self, 'log_delay_ms', 200)} ms", width=7)
        log_delay_scale = ttk.Scale(log_row, from_=0, to=600, orient=tk.HORIZONTAL, length=170)
        log_delay_scale.set(getattr(self, 'log_delay_ms', 200))
        log_delay_scale.configure(command=lambda v: log_delay_read.configure(text=f"{int(float(v))} ms"))
        log_delay_scale.pack(side=tk.LEFT, padx=(4, 6))
        log_delay_read.pack(side=tk.LEFT)
        ttk.Label(log_frame, text="Pause between log lines (0 = instant).",
                  style='Dim.TLabel').pack(anchor=tk.W, pady=(4, 0))

        # Difficulty
        diff_row = ttk.Frame(frm)
        diff_row.pack(anchor=tk.W, pady=(2, 4))
        ttk.Label(diff_row, text="Difficulty:").pack(side=tk.LEFT)
        diff_combo = ttk.Combobox(diff_row, values=list(DIFFICULTIES.keys()), state="readonly", width=10)
        diff_combo.set(getattr(self, 'difficulty', 'Normal'))
        diff_combo.pack(side=tk.LEFT, padx=(6, 0))

        # Adaptive difficulty: the quiet dial (combat.py, update_adaptive)
        adaptive_var = tk.BooleanVar(value=getattr(self, 'adaptive_enabled', True))
        ttk.Checkbutton(frm, text="Adaptive difficulty (eases packs off after rough fights, "
                                  "firms them up when you cruise)",
                        variable=adaptive_var).pack(anchor=tk.W, pady=(2, 4))

        # The narrator: spoken headlines for key moments (narrator.py). Uses
        # the system voice; also obeys the Enable Sound Effects switch above.
        narrator_var = tk.BooleanVar(value=getattr(self, 'narrator_enabled', True))
        ttk.Checkbutton(frm, text="Narrator: a voice speaks key events (damage taken, kills, "
                                  "boss warnings)",
                        variable=narrator_var).pack(anchor=tk.W, pady=(2, 4))

        # Autosave interval
        ttk.Label(frm, text="AutoSave interval (seconds):").pack(anchor=tk.W)
        interval_var = tk.StringVar(value=str(int(getattr(self, 'autosave_interval_ms', 30000) / 1000)))
        interval_entry = ttk.Entry(frm, textvariable=interval_var, width=10)
        interval_entry.pack(anchor=tk.W, pady=(2,6))

        # Save folder selection
        ttk.Label(frm, text="Save folder:").pack(anchor=tk.W)
        folder_var = tk.StringVar(value=getattr(self, 'save_folder', ''))
        folder_row = ttk.Frame(frm)
        folder_row.pack(fill=tk.X, pady=(2,6))
        folder_entry = ttk.Entry(folder_row, textvariable=folder_var)
        folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def choose_folder():
            p = filedialog.askdirectory(title="Select Save Folder", initialdir=getattr(self, 'save_folder', '.'))
            if p:
                folder_var.set(p)

        ttk.Button(folder_row, text="Browse", command=choose_folder).pack(side=tk.LEFT, padx=(6,0))

        def apply_settings():
            try:
                self.autosave_enabled = bool(autosave_var.get())
                self.sound_enabled = bool(sound_var.get())
                was_music = getattr(self, 'music_enabled', True)
                self.music_enabled = bool(music_var.get())
                if self.music_enabled and not was_music:
                    self.start_music()
                elif was_music and not self.music_enabled:
                    self.stop_music()
                self.music_volume = max(0, min(100, int(float(music_vol_scale.get()))))
                self.sfx_volume = max(0, min(100, int(float(sfx_vol_scale.get()))))
                self.apply_music_volume()
                self.apply_sfx_volume()
                self.log_delay_ms = max(0, min(2000, int(float(log_delay_scale.get()))))
                self.difficulty = diff_combo.get() or 'Normal'
                self.adaptive_enabled = bool(adaptive_var.get())
                was_narrating = getattr(self, 'narrator_enabled', True)
                self.narrator_enabled = bool(narrator_var.get())
                if self.narrator_enabled and not was_narrating:
                    self.narrate("Narrator on.")
                if self.sound_enabled:
                    self.play_sound('coin')  # little confirmation blip
                secs = max(1, int(float(interval_var.get())))
                self.autosave_interval_ms = int(secs * 1000)
                new_folder = folder_var.get().strip()
                if new_folder and new_folder != getattr(self, 'save_folder', ''):
                    try:
                        os.makedirs(new_folder, exist_ok=True)
                        self.save_folder = new_folder
                        self.quick_save_path = os.path.join(self.save_folder, 'quicksave.json')
                        self.autosave_path = os.path.join(self.save_folder, 'autosave.json')
                        self.settings_path = os.path.join(self.save_folder, 'settings.json')
                    except Exception:
                        pass
                # restart autosave with new interval/enable state
                if self.autosave_enabled:
                    self.start_autosave()
                else:
                    self.stop_autosave()
                self.save_settings()
                win.destroy()
            except Exception as e:
                messagebox.showerror("Settings Error", str(e))

        ttk.Button(frm, text="Apply", command=apply_settings).pack(side=tk.LEFT, pady=(6,0))
        ttk.Button(frm, text="Cancel", command=win.destroy).pack(side=tk.LEFT, pady=(6,0), padx=(6,0))
        self.place_window(win, min_w=430, min_h=460)
