"""The window: layout, theme, and everything that redraws it.

build_ui() creates every widget once, at startup, and stores the ones that
change on self (self.log, self.hp_bar, self.inventory_list...). Nothing else
in the game creates main-window widgets - they just call the refresh methods
below to update what build_ui already made.

THE THREE REFRESH METHODS - you will call these constantly

    refresh_stats()      name, HP/XP bars, abilities, AC, class status line
    refresh_inventory()  the item list and its description panel
    refresh_buttons()    which buttons are shown and which are greyed out

After changing game state, call the ones affected. They are cheap and safe to
call repeatedly, so err on the side of calling them.

log_message() is the game's voice - it is called over 200 times. The `color`
argument picks a style: 'player', 'enemy', 'important', 'warning', or none.

WHERE TO CHANGE THINGS

    Window layout / new widgets ..... build_ui
    Colours ......................... PAL (top of the class)
    Which buttons appear when ....... refresh_buttons
    The character panel text ........ refresh_stats
    Log message colours ............. log_message
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (SUBCLASSES, WEAPONS, FINESSE, RANGED, ARMOR, SHIELDS, MAGIC_ITEMS,
                   EQUIP_SLOTS, SLOT_ATTR, CLASSES, DIFFICULTIES, CLASS_SPELLS,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, SPELL_CATALOG, SPELL_LEVELS, ASI_LEVELS)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class UIMixin:

    PAL = {
        'bg':     '#241f1a',   # deep umber background
        'panel':  '#3a3128',   # raised surfaces (buttons)
        'field':  '#1b1712',   # log / list / bar backgrounds
        'text':   '#e8e0cf',   # parchment text
        'dim':    '#a89b85',   # secondary text
        'gold':   '#e0b64a',   # headings, gold
        'accent': '#c8842a',   # borders, hover
        'hp_hi':  '#5aa85e',
        'hp_mid': '#e0b64a',
        'hp_lo':  '#e05a50',
        'xp':     '#7e57c2',
    }

    def apply_theme(self):
        """Dark dungeon theme for the whole app."""
        p = self.PAL
        self.root.configure(bg=p['bg'])
        # popup windows (shop, rest, decisions...) inherit the dark background
        self.root.option_add('*Toplevel.background', p['bg'])
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')  # the theme that best supports recoloring
        except Exception:
            pass
        style.configure('.', background=p['bg'], foreground=p['text'], font=("Segoe UI", 10))
        style.configure('TFrame', background=p['bg'])
        style.configure('TLabel', background=p['bg'], foreground=p['text'])
        style.configure('Title.TLabel', foreground=p['gold'], font=("Segoe UI", 18, "bold"))
        style.configure('Gold.TLabel', foreground=p['gold'])
        style.configure('Dim.TLabel', foreground=p['dim'])
        style.configure('TLabelframe', background=p['bg'], bordercolor=p['accent'])
        style.configure('TLabelframe.Label', background=p['bg'], foreground=p['gold'],
                        font=("Segoe UI", 10, "bold"))
        style.configure('TButton', background=p['panel'], foreground=p['text'],
                        bordercolor=p['accent'], focuscolor=p['panel'], padding=(8, 4))
        style.map('TButton',
                  background=[('disabled', p['field']), ('active', p['accent'])],
                  foreground=[('disabled', p['dim']), ('active', '#1b1712')])
        style.configure('TEntry', fieldbackground=p['field'], foreground=p['text'],
                        insertcolor=p['text'], bordercolor=p['accent'])
        style.configure('TCheckbutton', background=p['bg'], foreground=p['text'])
        style.map('TCheckbutton', background=[('active', p['bg'])])
        style.configure('TRadiobutton', background=p['bg'], foreground=p['text'])
        style.map('TRadiobutton', background=[('active', p['bg'])])
        style.configure('TCombobox', fieldbackground=p['field'], foreground=p['text'],
                        background=p['panel'], arrowcolor=p['text'])
        # readonly/disabled/focused fields must stay dark too, or the parchment
        # text lands on a white field and becomes unreadable
        style.map('TCombobox',
                  fieldbackground=[('readonly', p['field']), ('disabled', p['bg'])],
                  foreground=[('disabled', p['dim'])],
                  selectbackground=[('!disabled', p['field'])],
                  selectforeground=[('!disabled', p['text'])],
                  background=[('active', p['accent'])])
        # TSpinbox was never styled at all: clam's default white field plus the
        # global parchment foreground made every level picker white-on-white
        style.configure('TSpinbox', fieldbackground=p['field'], foreground=p['text'],
                        background=p['panel'], arrowcolor=p['text'],
                        insertcolor=p['text'], bordercolor=p['accent'])
        style.map('TSpinbox',
                  fieldbackground=[('readonly', p['field']), ('disabled', p['bg'])],
                  foreground=[('disabled', p['dim'])],
                  arrowcolor=[('pressed', '#1b1712')])
        style.map('TEntry',
                  fieldbackground=[('disabled', p['bg'])],
                  selectbackground=[('!disabled', p['accent'])],
                  selectforeground=[('!disabled', '#1b1712')])
        style.configure('TNotebook', background=p['bg'], bordercolor=p['accent'],
                        tabmargins=(6, 4, 6, 0))
        style.configure('TNotebook.Tab', background=p['panel'], foreground=p['text'],
                        padding=(14, 6), font=("Segoe UI", 10, "bold"))
        style.map('TNotebook.Tab',
                  background=[('selected', p['accent'])],
                  foreground=[('selected', '#1b1712')])
        for sb in ('Vertical.TScrollbar', 'Horizontal.TScrollbar'):
            style.configure(sb, background=p['panel'], troughcolor=p['field'],
                            bordercolor=p['bg'], arrowcolor=p['text'])
            style.map(sb, background=[('active', p['accent'])])
        style.configure('Horizontal.TScale', background=p['bg'], troughcolor=p['field'])
        style.configure('TSeparator', background=p['accent'])
        # a Combobox's drop-down list is a plain tk listbox; recolor it to match
        self.root.option_add('*TCombobox*Listbox.background', p['field'])
        self.root.option_add('*TCombobox*Listbox.foreground', p['text'])
        self.root.option_add('*TCombobox*Listbox.selectBackground', p['accent'])
        self.root.option_add('*TCombobox*Listbox.selectForeground', '#1b1712')
        # readable fallbacks for any plain tk widget a popup forgets to color
        for pattern, value in (('*Listbox.background', p['field']),
                               ('*Listbox.foreground', p['text']),
                               ('*Listbox.selectBackground', p['accent']),
                               ('*Listbox.selectForeground', '#1b1712'),
                               ('*Text.background', p['field']),
                               ('*Text.foreground', p['text']),
                               ('*Text.insertBackground', p['text']),
                               ('*Entry.background', p['field']),
                               ('*Entry.foreground', p['text']),
                               ('*Entry.insertBackground', p['text']),
                               ('*Canvas.background', p['bg'])):
            self.root.option_add(pattern, value)

    # ------------------------------------------------------- window helpers

    def make_popup(self, title, parent=None, modal=True):
        """One themed Toplevel, made the same way everywhere.

        Every dialog goes through here so they all share the dark theme, the
        right parent and, via place_window, a size that actually fits the
        screen.
        
"""
        parent = parent or self.root
        win = tk.Toplevel(parent)
        win.title(title)
        win.configure(bg=self.PAL['bg'])
        win.transient(parent)
        if modal:
            try:
                win.grab_set()
            except Exception:
                pass
        return win

    def place_window(self, win, parent=None, min_w=0, min_h=0, pad_w=28, pad_h=28):
        """Size a window to its content, clamp it to the screen, and centre it.

        This replaces the geometry maths that used to be copied into each
        dialog by hand - and unlike those copies it guarantees a window can
        never open wider or taller than the screen, or hang off its edge.
        
"""
        parent = parent or self.root
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        max_w, max_h = int(sw * 0.92), int(sh * 0.88)   # leave room for the taskbar
        w = max(min(min_w, max_w), min(win.winfo_reqwidth() + pad_w, max_w))
        h = max(min(min_h, max_h), min(win.winfo_reqheight() + pad_h, max_h))
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
        except Exception:
            x = (sw - w) // 2
            y = (sh - h) // 2
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        try:
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.minsize(min(380, w), min(300, h))
        except Exception:
            pass
        return win

    def make_scrollable(self, parent, height=None):
        """A vertical scrolling area; returns the frame to build content into.

        Includes mouse-wheel support, which the hand-made canvases lacked, and
        stretches its content to the visible width so wrapped labels behave.
        
"""
        kwargs = {'height': height} if height else {}
        canvas = tk.Canvas(parent, highlightthickness=0, bg=self.PAL['bg'], **kwargs)
        vbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))

        def _wheel(event):
            try:
                if not canvas.winfo_exists():
                    return
                step = -1 if (getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0) else 1
                canvas.yview_scroll(step, "units")
            except Exception:
                pass
            return "break"

        def _bind_wheel(_e=None):
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                try:
                    canvas.bind_all(seq, _wheel)
                except Exception:
                    pass

        def _unbind_wheel(_e=None):
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                try:
                    canvas.unbind_all(seq)
                except Exception:
                    pass

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)
        canvas.bind("<Destroy>", _unbind_wheel)
        return inner

    # ----------------------------------------------- the one character window

    SHEET_TABS = (('sheet', 'Character'), ('spells', 'Spellbook'), ('gear', 'Gear'))

    def open_sheet(self, tab='sheet'):
        """One window for the character sheet, the spellbook and the gear screen.

        These used to be three separate windows; now they are tabs of a single
        one. Opening any of them while the window is already up just switches
        tab instead of stacking another window on the screen.
        
"""
        win = getattr(self, '_sheet_win', None)
        if not (win and win.winfo_exists()):
            win = self.make_popup(f"{self.name} \u2014 Character")
            self._sheet_win = win
            nb = ttk.Notebook(win)
            nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
            self._sheet_nb = nb
            self._sheet_frames = {}
            for key, label in self.SHEET_TABS:
                f = ttk.Frame(nb, padding=6)
                nb.add(f, text=label)
                self._sheet_frames[key] = f
            self._sheet_switching = False
            nb.bind('<<NotebookTabChanged>>', self._on_sheet_tab_changed)
            ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 8))
        keys = [k for k, _ in self.SHEET_TABS]
        self._sheet_switching = True
        try:
            self._sheet_nb.select(keys.index(tab))
        finally:
            self._sheet_switching = False
        self._rebuild_sheet_tab(tab)
        self.place_window(win, min_w=620, min_h=560)
        try:
            win.lift()
        except Exception:
            pass
        return win

    def _on_sheet_tab_changed(self, _event=None):
        """Rebuild a tab's content when the player clicks onto it."""
        if getattr(self, '_sheet_switching', False):
            return
        try:
            idx = self._sheet_nb.index(self._sheet_nb.select())
            self._rebuild_sheet_tab(self.SHEET_TABS[idx][0])
        except Exception:
            pass

    def _rebuild_sheet_tab(self, key):
        """Clear one tab and build its current content fresh."""
        frame = self._sheet_frames.get(key)
        if frame is None or not frame.winfo_exists():
            return
        for w in frame.winfo_children():
            w.destroy()
        if key == 'sheet':
            self._build_sheet_tab(frame)
        elif key == 'spells':
            self._build_spellbook_tab(frame)
        elif key == 'gear':
            self._build_gear_tab(frame)

    def close_sheet(self):
        """Close the character window if it is open (a cast, say, ends the browse)."""
        win = getattr(self, '_sheet_win', None)
        if win and win.winfo_exists():
            try:
                win.destroy()
            except Exception:
                pass

    def build_ui(self):
        """Create every widget in the main window, once, at startup.

        Widgets that later change are stored on self so the refresh_* methods can
        update them. To add something to the main window, this is the place.
        
"""
        self.apply_theme()
        p = self.PAL
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Tiny Adventure", style='Title.TLabel').pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(main_frame,
                  text="Explore the dungeon room by room: fight monsters, disarm traps, loot chests, and descend ever deeper.",
                  wraplength=640, justify=tk.LEFT, style='Dim.TLabel').pack(anchor=tk.W)

        name_frame = ttk.Frame(main_frame)
        name_frame.pack(fill=tk.X, pady=(10, 8))
        ttk.Label(name_frame, text="Name:").pack(side=tk.LEFT)
        self.name_entry = ttk.Entry(name_frame, width=24)
        self.name_entry.pack(side=tk.LEFT, padx=(6, 0))
        self.name_entry.bind("<Return>", lambda event: self.start_game())
        ttk.Button(name_frame, text="Start / Reset", command=self.start_game).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(name_frame, text="Menu", command=self.open_main_menu).pack(side=tk.LEFT, padx=(6, 0))

        # music volume: accessible via Settings and hotkeys (- / +)
        for key in ('<minus>', '<KP_Subtract>'):
            self.root.bind(key, lambda e: self.nudge_music_volume(-10))
        for key in ('<plus>', '<equal>', '<KP_Add>'):
            self.root.bind(key, lambda e: self.nudge_music_volume(10))

        stats_frame = ttk.LabelFrame(main_frame, text="Character", padding=(10, 8))
        stats_frame.pack(fill=tk.X, pady=(8, 8))
        # dice tray on the right; character info on the left
        self.dice_canvas = tk.Canvas(stats_frame, width=78, height=88, bg=p['field'], highlightthickness=0)
        self.dice_canvas.pack(side=tk.RIGHT, padx=(10, 0))
        stats_inner = ttk.Frame(stats_frame)
        stats_inner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        stats_frame = stats_inner  # existing label code below attaches to the inner frame
        self.name_label = ttk.Label(stats_frame, text="", style='Gold.TLabel', font=("Segoe UI", 11, "bold"))
        self.name_label.pack(anchor=tk.W)

        bar_row = ttk.Frame(stats_frame)
        bar_row.pack(fill=tk.X, pady=(4, 4))
        ttk.Label(bar_row, text="HP", width=3).pack(side=tk.LEFT)
        self.hp_bar = tk.Canvas(bar_row, height=18, width=230, bg=p['field'], highlightthickness=0)
        self.hp_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 14))
        ttk.Label(bar_row, text="XP", width=3).pack(side=tk.LEFT)
        self.xp_bar = tk.Canvas(bar_row, height=18, width=230, bg=p['field'], highlightthickness=0)
        self.xp_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        self.hp_bar.bind("<Configure>", lambda e: self.update_bars())
        self.xp_bar.bind("<Configure>", lambda e: self.update_bars())

        self.gold_label = ttk.Label(stats_frame, text="", style='Gold.TLabel')
        self.gold_label.pack(anchor=tk.W)
        # what you are wearing, in full - press Gear to change any of it
        self.gear_label = ttk.Label(stats_frame, text="", wraplength=560, justify=tk.LEFT)
        self.gear_label.pack(anchor=tk.W)
        self.ability_label = ttk.Label(stats_frame, text="")
        self.ability_label.pack(anchor=tk.W)
        self.ability_label_2 = ttk.Label(stats_frame, text="")
        self.ability_label_2.pack(anchor=tk.W)
        self.combat_label = ttk.Label(stats_frame, text="")
        self.combat_label.pack(anchor=tk.W)
        self.class_status_label = ttk.Label(stats_frame, text="", style='Dim.TLabel')
        self.class_status_label.pack(anchor=tk.W)

        # combat panel: created hidden, shown only during fights
        self.combat_frame = ttk.LabelFrame(main_frame, text="Combat \u2014 click an enemy to target it", padding=(8, 6))
        self.combat_canvas = tk.Canvas(self.combat_frame, height=118, bg=p['field'], highlightthickness=0)
        self.combat_canvas.pack(fill=tk.X)
        self.combat_panel_visible = False

        self.buttons_frame = buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(4, 8))
        for text, command in [
            ("Explore", self.do_explore),
            ("Rest", self.do_rest),
            ("Attack", self.do_attack),
            ("Class Ability", self.use_class_ability),
            ("Bonus Action", self.open_bonus_menu),
            ("Move", self.open_move_menu),
            ("Quick Attack", self.do_quick_attack),
            ("Heavy Strike", self.do_heavy_attack),
            ("Precise Attack", self.do_precise_attack),
            ("End Turn", self.end_turn),
            ("Flee", self.do_flee),
            ("Spells", self.open_spellbook),
            ("Use Item", self.do_use_item),
            ("Gear", self.open_equipment_window),
            ("Shop", self.do_shop),
            ("Stats", self.show_stats),
            ("Help", self.show_help),
        ]:
            button = ttk.Button(buttons_frame, text=text, command=command)
            button.pack(side=tk.LEFT, padx=(0, 6))
            self.buttons[text] = button

        inventory_frame = ttk.LabelFrame(main_frame, text="Inventory  (select an item to read it, then Use Item)", padding=(10, 8))
        inventory_frame.pack(fill=tk.BOTH, expand=True)
        self.inventory_list = tk.Listbox(inventory_frame, height=5, bg=p['field'], fg=p['text'],
                                         selectbackground=p['accent'], selectforeground='#1b1712',
                                         relief=tk.FLAT, highlightthickness=0,
                                         font=("Segoe UI", 10), activestyle='none')
        self.inventory_list.pack(fill=tk.BOTH, expand=True)
        self.inventory_list.bind("<Double-Button-1>", lambda e: self.do_use_item())
        self.inventory_list.bind("<<ListboxSelect>>", lambda e: self.show_item_details())
        # description of whichever item is highlighted
        self.item_detail_label = ttk.Label(inventory_frame, text="Select an item to see what it does.",
                                           style='Dim.TLabel', wraplength=640, justify=tk.LEFT)
        self.item_detail_label.pack(anchor=tk.W, pady=(6, 0))

        log_frame = ttk.LabelFrame(main_frame, text="Log", padding=(10, 8))
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log = scrolledtext.ScrolledText(log_frame, height=9, wrap=tk.WORD,
                                             bg=p['field'], fg=p['text'], insertbackground=p['text'],
                                             relief=tk.FLAT, font=("Segoe UI", 10))
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.configure(state="disabled")

    def update_bars(self):
        """Redraw the HP and XP bars from current values."""
        if not hasattr(self, 'hp_bar'):
            return
        p = self.PAL
        created = getattr(self, 'character_created', False)

        c = self.hp_bar
        c.delete('all')
        w = c.winfo_width() if c.winfo_width() > 1 else int(c['width'])
        h = int(c['height'])
        if created and getattr(self, 'max_health', 0) > 0:
            frac = max(0.0, min(1.0, self.health / self.max_health))
            color = p['hp_hi'] if frac > 0.5 else (p['hp_mid'] if frac > 0.25 else p['hp_lo'])
            c.create_rectangle(0, 0, int(w * frac), h, fill=color, outline='')
            c.create_text(w // 2, h // 2, text=f"{self.health} / {self.max_health}",
                          fill=p['text'], font=("Segoe UI", 9, "bold"))

        c = self.xp_bar
        c.delete('all')
        w = c.winfo_width() if c.winfo_width() > 1 else int(c['width'])
        if created:
            frac = max(0.0, min(1.0, self.xp / max(1, self.xp_to_next)))
            c.create_rectangle(0, 0, int(w * frac), h, fill=p['xp'], outline='')
            c.create_text(w // 2, h // 2, text=f"Lvl {self.player_level}  \u2022  {self.xp}/{self.xp_to_next} XP",
                          fill=p['text'], font=("Segoe UI", 9, "bold"))

    def show_dice_roll(self, final, sides=20, label="d20"):
        """Animate a die tumbling in the dice tray, settling on the real result."""
        c = getattr(self, 'dice_canvas', None)
        if c is None:
            return
        self.play_sound('dice')
        self._dice_seq = getattr(self, '_dice_seq', 0) + 1
        seq = self._dice_seq
        p = self.PAL

        def draw(num, settled):
            try:
                c.delete('all')
            except Exception:
                return
            pts = [39, 6, 70, 24, 70, 56, 39, 74, 8, 56, 8, 24]
            if settled and num == sides:
                outline, col = p['gold'], p['gold']
            elif settled and num == 1:
                outline, col = p['hp_lo'], p['hp_lo']
            else:
                outline, col = p['accent'], p['text']
            c.create_polygon(pts, fill='#3a3128', outline=outline, width=3 if settled else 2)
            c.create_text(39, 40, text=str(num), fill=col, font=("Segoe UI", 17, "bold"))
            c.create_text(39, 82, text=label, fill=p['dim'], font=("Segoe UI", 8))

        def anim(step=0):
            if seq != getattr(self, '_dice_seq', 0):
                return  # a newer roll took over the tray
            if step < 8:
                draw(random.randint(1, sides), False)
                try:
                    self.root.after(45, lambda: anim(step + 1))
                except Exception:
                    pass
            else:
                draw(final, True)
        anim()

    def refresh_stats(self):
        """Redraw the character panel: name, bars, abilities, AC, class status.

        Recomputes derived stats first, so this always shows current truth.
        
"""
        try:
            self.update_derived_stats()
            if not getattr(self, 'character_created', False):
                self.name_label.configure(text="No character yet \u2014 press Start / Reset or open the Menu")
                self.gold_label.configure(text="")
                self.gear_label.configure(text="")
                self.ability_label.configure(text="")
                self.ability_label_2.configure(text="")
                self.combat_label.configure(text="")
                self.update_bars()
                return

            name_text = f"Name: {self.name}"
            if getattr(self, 'char_class', None):
                path = f"{self.subclass} " if getattr(self, 'subclass', None) else ""
                name_text += f" - {path}{self.char_class} {self.player_level}"
            self.name_label.configure(text=name_text)
            # a full line for what you are actually wearing, all four slots
            worn = [f"{getattr(self, 'equipped_weapon', None) or 'unarmed'} (d{self.player_damage_dice})"]
            for slot in ('armor', 'shield', 'trinket'):
                item = getattr(self, SLOT_ATTR[slot], None)
                if item:
                    worn.append(item)
                else:
                    worn.append(f"no {slot}")
            self.gear_label.configure(text="Wearing: " + "  |  ".join(worn))
            self.gold_label.configure(text=f"Gold: {self.gold}")
            self.update_bars()
            self.ability_label.configure(
                text=f"STR: {self.strength}   DEX: {self.dexterity}   CON: {self.constitution}"
            )
            self.ability_label_2.configure(
                text=f"INT: {self.intelligence}   WIS: {self.wisdom}   CHA: {self.charisma}   END: {self.endurance}"
            )
            combat_bits = [f"AC: {self.player_ac}",
                           f"Attack: +{self.player_attack_bonus}",
                           f"Damage: 1d{self.player_damage_dice}+{self.player_damage_bonus}"]
            if getattr(self, 'damage_reduction', 0):
                combat_bits.append(f"DR: {self.damage_reduction}")
            if getattr(self, 'temp_hp', 0):
                combat_bits.append(f"Temp HP: {self.temp_hp}")
            self.combat_label.configure(text="   ".join(combat_bits))
            # Class/level status
            if getattr(self, 'character_created', False):
                status_parts = [f"Lvl {self.player_level}", f"XP: {self.xp}/{self.xp_to_next}"]
                # Hit Dice: how many short rests you still have in you
                hd = getattr(self, 'hit_dice', 0)
                hd_max = getattr(self, 'hit_dice_max', getattr(self, 'player_level', 1))
                status_parts.append(f"Hit Dice: {hd}/{hd_max} (d{getattr(self, 'class_hit_die', 8)})")
                comp = getattr(self, 'companion', None)
                if comp:
                    status_parts.append(f"Ally: {comp['name']} the {comp['title']} "
                                        f"({comp['hp']}/{self.companion_max_hp()} HP)")
                if self.char_class == 'Rogue':
                    status_parts.append(f"Sneak: {'Ready' if self.sneak_available else 'Used'}")
                if self.char_class == 'Fighter':
                    status_parts.append(f"2ndWind: {'Ready' if self.second_wind_available else 'Used'}")
                    status_parts.append(f"ActionSurge: {'Ready' if self.action_surge_available else 'Used'}")
                if getattr(self, 'caster_type', None):
                    # display per-level slot counts and known spells
                    slots = getattr(self, 'spell_slots_by_level', {1: 0, 2: 0, 3: 0})
                    maxs = getattr(self, 'spell_slots_max_by_level', {})
                    try:
                        known = ", ".join([self.spell_catalog[k][0] for k in getattr(self, 'known_spells', []) if k in self.spell_catalog])
                    except Exception:
                        known = ""
                    slot_bits = [f"L{lvl}:{slots.get(lvl,0)}/{maxs.get(lvl,0)}"
                                 for lvl in SPELL_LEVELS if maxs.get(lvl, 0)]
                    if slot_bits:
                        status_parts.append("Slots " + " ".join(slot_bits))
                    if known:
                        if len(known) > 90:
                            known = known[:90].rsplit(', ', 1)[0] + ", ... (see Spells)"
                        status_parts.append(f"Spells: {known}")
                if getattr(self, 'haste_active', False):
                    status_parts.append(f"HASTED ({self.haste_rounds} rds)")
                if getattr(self, 'asi_pending', 0):
                    status_parts.append("ABILITY SCORE IMPROVEMENT WAITING")
                for flag, text in (('death_ward', 'Death Ward'),
                                   ('beacon_of_hope', 'Beacon of Hope'),
                                   ('escape_ready', 'Escape ready'),
                                   ('rage_active', 'Raging'),
                                   ('hunters_mark', "Hunter's Mark"),
                                   ('hex_spell_active', 'Hexed'),
                                   ('guidance_ready', 'Guidance')):
                    if getattr(self, flag, False):
                        status_parts.append(text)
                if getattr(self, 'poisoned', 0):
                    status_parts.append(f"POISONED ({self.poisoned})")
                if getattr(self, 'cursed_rounds', 0):
                    status_parts.append(f"CURSED ({self.cursed_rounds})")
                if getattr(self, 'can_long_rest', False):
                    status_parts.append("Camp: Rest available")
                self.class_status_label.configure(text=' | '.join(status_parts))
            else:
                self.class_status_label.configure(text='')
        except Exception as e:
            # Log the error and show a minimal fallback so the UI doesn't break
            try:
                self.log_message(f"Error updating stats: {e}", color='warning')
            except Exception:
                pass
            self.name_label.configure(text=f"Name: {getattr(self, 'name', 'Adventurer')}")
            self.gold_label.configure(text=f"Gold: {getattr(self, 'gold', 0)}")
            self.update_bars()
            self.ability_label.configure(text="")
            self.ability_label_2.configure(text="")
            self.combat_label.configure(text="")

    def refresh_buttons(self):
        """Show, hide and grey out buttons to match the situation.

        This is what enforces the action economy visually: attack buttons grey out
        once your action is spent, the bonus button once your bonus is spent. In
        combat you get attack buttons; out of combat, Explore and Rest.
        
"""
        for bname in ("Attack", "Quick Attack", "Heavy Strike", "Precise Attack", "Shop",
                      "Class Ability", "Bonus Action", "Move", "End Turn", "Use Item", "Rest",
                      "Explore", "Spells", "Flee", "Gear"):
            self.buttons[bname].pack_forget()
            self.buttons[bname].state(['!disabled'])
        self.buttons["Stats"].pack(side=tk.LEFT, padx=(0, 6))
        self.buttons["Help"].pack(side=tk.LEFT, padx=(0, 6))

        # Before a character exists, only Stats and Help are useful
        if not getattr(self, 'character_created', False):
            return

        if self.in_combat:
            busy = getattr(self, 'enemy_attack_pending', False)
            atk_state = ['!disabled'] if (self.player_action_available and not busy) else ['disabled']
            bon_state = ['!disabled'] if (self.player_bonus_available and not busy) else ['disabled']
            end_state = ['!disabled'] if not busy else ['disabled']
            for nm in ("Quick Attack", "Heavy Strike", "Precise Attack"):
                self.buttons[nm].state(atk_state)
                self.buttons[nm].pack(side=tk.LEFT, padx=(0, 6))
            self.buttons["Bonus Action"].state(bon_state)
            self.buttons["Bonus Action"].pack(side=tk.LEFT, padx=(0, 6))
            move_state = ['!disabled'] if (getattr(self, 'player_move_available', True)
                                           and not busy) else ['disabled']
            self.buttons["Move"].state(move_state)
            self.buttons["Move"].pack(side=tk.LEFT, padx=(0, 6))
            if getattr(self, 'char_class', None):
                self.buttons["Class Ability"].pack(side=tk.LEFT, padx=(0, 6))
            self.buttons["End Turn"].state(end_state)
            self.buttons["End Turn"].pack(side=tk.LEFT, padx=(0, 6))
            # running away is always on the table, right up until the enemies swing
            self.buttons["Flee"].state(end_state)
            self.buttons["Flee"].pack(side=tk.LEFT, padx=(0, 6))
        else:
            self.buttons["Explore"].pack(side=tk.LEFT, padx=(0, 6))
            self.buttons["Rest"].pack(side=tk.LEFT, padx=(0, 6))
            if self.current_event == "enemy":
                self.buttons["Attack"].pack(side=tk.LEFT, padx=(0, 6))
            if self.shop_available or self.current_event == "shop":
                self.buttons["Shop"].pack(side=tk.LEFT, padx=(0, 6))
        # casters can open their spellbook at any time; out of combat only
        # utility and healing spells will actually be castable
        if self.class_spell_list():
            self.buttons["Spells"].pack(side=tk.LEFT, padx=(0, 6))
        if self.inventory:
            self.buttons["Use Item"].pack(side=tk.LEFT, padx=(0, 6))
        self.buttons["Gear"].pack(side=tk.LEFT, padx=(0, 6))
        self.draw_combat()

    def log_message(self, message, color="black", bold=False):
        """Write a line to the game log - the main way the game talks to the player.

        color: 'player', 'enemy', 'important', 'warning', or omitted for plain text.

        Lines are no longer all drawn in the same instant. When several arrive
        together (a combat round, opening a chest) they are queued and revealed
        one at a time, self.log_delay_ms apart, so the player can follow what
        happened. The first line of a burst still appears immediately, so single
        messages feel as snappy as before. Set log_delay_ms to 0 (Settings, or
        directly as the soak test does) for the old everything-at-once behaviour.
        
"""
        delay = max(0, int(getattr(self, 'log_delay_ms', 200)))
        queue = getattr(self, '_log_queue', None)
        if queue is None:
            queue = self._log_queue = []
        if delay == 0:
            # pacing off: flush anything still waiting, then this line, all now.
            # This keeps headless runs (no mainloop, so after() never fires)
            # fully synchronous, and is what "0 ms" in Settings means.
            self._log_pump_running = False
            while queue:
                queued_message, queued_color = queue.pop(0)
                self._log_write_now(queued_message, queued_color)
            self._log_write_now(message, color)
            return
        queue.append((message, color))
        if not getattr(self, '_log_pump_running', False):
            self._log_pump_running = True
            self._log_pump()  # show the first queued line right away

    def _log_pump(self):
        """Draw the next queued log line, then come back for the one after it.

        Runs itself via root.after until the queue stays empty for one interval;
        that trailing tick means a line arriving moments after a burst is still
        spaced away from it rather than appearing back-to-back.
        
"""
        queue = getattr(self, '_log_queue', None) or []
        if not queue:
            self._log_pump_running = False
            return
        message, color = queue.pop(0)
        self._log_write_now(message, color)
        delay = max(1, int(getattr(self, 'log_delay_ms', 200)))
        try:
            self.root.after(delay, self._log_pump)
        except Exception:
            # window is going away mid-burst; just stop cleanly
            self._log_pump_running = False

    def _log_write_now(self, message, color):
        """Actually put one line into the log widget (only log_message calls this)."""
        try:
            self.log.configure(state="normal")
            self.log.tag_configure("player", foreground="#81c784", font=("Segoe UI", 10, "bold"))
            self.log.tag_configure("enemy", foreground="#e57373", font=("Segoe UI", 10, "bold"))
            self.log.tag_configure("important", foreground="#7ec2f0", font=("Segoe UI", 10, "bold"))
            self.log.tag_configure("warning", foreground="#ffb74d", font=("Segoe UI", 10, "bold"))

            tag = None
            if color == "player":
                tag = "player"
            elif color == "enemy":
                tag = "enemy"
            elif color == "important":
                tag = "important"
            elif color == "warning":
                tag = "warning"

            self.log.insert(tk.END, message + "\n", (tag,) if tag else None)
            self.log.configure(state="disabled")
            self.log.yview(tk.END)
        except tk.TclError:
            pass  # widget already destroyed during shutdown

    def float_text(self, x, y, text, color):
        """Animate a damage/heal number floating up from (x, y) on the combat canvas."""
        if not getattr(self, 'combat_panel_visible', False):
            return
        c = self.combat_canvas
        tid = c.create_text(x, y, text=text, fill=color, font=("Segoe UI", 12, "bold"))

        def step(n=0):
            try:
                c.move(tid, 0, -2)
                if n < 12:
                    self.root.after(35, lambda: step(n + 1))
                else:
                    c.delete(tid)
            except Exception:
                pass
        step()

    def flash_card(self, idx, color='#e05a50'):
        """Briefly flash an enemy card to show it was hit."""
        if not getattr(self, 'combat_panel_visible', False):
            return
        c = self.combat_canvas
        x = self.card_x(idx)
        rid = c.create_rectangle(x, 8, x + 170, 110, fill=color, stipple='gray50', outline='')

        def clear():
            try:
                c.delete(rid)
            except Exception:
                pass
        self.root.after(140, clear)

    def flash_death_screen(self):
        """Flash the screen red, then reset the game."""
        self.root.update_idletasks()
        flash = tk.Toplevel(self.root)
        flash.overrideredirect(True)
        flash.attributes("-topmost", True)
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        flash.geometry(f"{width}x{height}+{x}+{y}")
        flash.configure(bg="red")
        flash.lift()
        flash.after(900, flash.destroy)
        flash.after(1200, self.reset_game)

    def show_stats(self):
        """Open the character window on its Character Sheet tab.

        The sheet, the spellbook and the gear screen share one tabbed window
        now, so this and its siblings stop stacking separate windows.
        
"""
        self.open_sheet('sheet')

    def _build_sheet_tab(self, container):
        """The full character sheet: vitals, abilities, equipment, resources, effects.

        This is the "what am I actually carrying and what is it doing" screen. Ability
        scores show the base you rolled and, separately, whatever your gear is adding,
        so it is always clear where a number came from.
        
"""
        content = self.make_scrollable(container)

        def section(title):
            box = ttk.LabelFrame(content, text=title, padding=8)
            box.pack(fill=tk.X, pady=(4, 4))
            return box

        def line(parent, text, style=None, bold=False):
            kwargs = {'wraplength': 470, 'justify': tk.LEFT}
            if style:
                kwargs['style'] = style
            if bold:
                kwargs['font'] = ("Segoe UI", 10, "bold")
            ttk.Label(parent, text=text, **kwargs).pack(anchor=tk.W)

        if not getattr(self, 'character_created', False):
            line(content, "No character yet. Press Start / Reset, or use Quick Start in the Menu.")
            return

        self.update_derived_stats()
        gear = self.gear_effects()

        # ---------------------------------------------------------- identity
        ttk.Label(content, text=f"{self.name}", style='Title.TLabel').pack(anchor=tk.W)
        _path = f" \u2014 {self.subclass}" if getattr(self, 'subclass', None) else ""
        ttk.Label(content, text=f"Level {self.player_level} {self.char_class or 'Adventurer'}{_path}"
                                f"   \u2022   {self.xp}/{self.xp_to_next} XP"
                                f"   \u2022   {self.gold} gold",
                  style='Gold.TLabel').pack(anchor=tk.W, pady=(0, 6))
        if getattr(self, 'subclass', None):
            _sd = SUBCLASSES.get(self.char_class, {}).get(self.subclass, {}).get('desc', '')
            if _sd:
                ttk.Label(content, text=_sd, style='Dim.TLabel', wraplength=470,
                          justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 6))

        # ------------------------------------------------------------ vitals
        box = section("Vitals")
        hp_line = f"Health: {self.health} / {self.max_health}"
        if getattr(self, 'temp_hp', 0):
            hp_line += f"   (+{self.temp_hp} temporary)"
        line(box, hp_line, bold=True)
        line(box, f"Armor Class: {self.player_ac}")
        line(box, f"Attack Bonus: +{self.player_attack_bonus}")
        line(box, f"Damage: 1d{self.player_damage_dice} + {self.player_damage_bonus}")
        if getattr(self, 'damage_reduction', 0):
            line(box, f"Damage Reduction: {self.damage_reduction} off every hit you take")
        if gear.get('crit_range', 20) < 20:
            line(box, f"Critical Hits: on a roll of {gear['crit_range']} or better")
        if gear.get('regen'):
            line(box, f"Regeneration: {gear['regen']} HP at the start of each combat round")

        # --------------------------------------------------------- abilities
        box = section("Abilities")
        for label, key in (("STR", 'strength'), ("DEX", 'dexterity'), ("CON", 'constitution'),
                           ("INT", 'intelligence'), ("WIS", 'wisdom'), ("CHA", 'charisma'),
                           ("END", 'endurance')):
            base = getattr(self, key, 10)
            bonus = gear.get('stat', {}).get(key, 0)
            total = base + bonus
            text = f"{label}: {total} ({self.ability_modifier(total):+d})"
            if bonus:
                text += f"    \u2014 {base} base, +{bonus} from your gear"
            line(box, text)
        if getattr(self, 'asi_pending', 0):
            line(box, f"You have {self.asi_pending} unspent Ability Score Improvement(s). "
                      "They open automatically, or you can level up again to stack them.",
                 style='Gold.TLabel')

        # --------------------------------------------------------- equipment
        box = section("Equipment  (press Gear to change any of it)")
        for slot in EQUIP_SLOTS:
            item = getattr(self, SLOT_ATTR[slot], None)
            if not item:
                line(box, f"{slot.title()}: (empty)", style='Dim.TLabel')
                continue
            line(box, f"{slot.title()}: {item}", bold=True)
            line(box, "    " + self.describe_item(item), style='Dim.TLabel')

        # ---------------------------------------------------------- resources
        box = section("Resources")
        hd = getattr(self, 'hit_dice', 0)
        hd_max = getattr(self, 'hit_dice_max', getattr(self, 'player_level', 1))
        die = getattr(self, 'class_hit_die', 8)
        line(box, f"Hit Dice: {hd} of {hd_max} remaining (d{die} each)", bold=True)
        line(box, "    Each one is a Short Rest that heals 1d%d + your CON modifier. "
                  "A Long Rest at a camp gets them all back." % die, style='Dim.TLabel')
        if getattr(self, 'caster_type', None):
            slots = getattr(self, 'spell_slots_by_level', {})
            maxs = getattr(self, 'spell_slots_max_by_level', {})
            any_slots = False
            for lvl in SPELL_LEVELS:
                if maxs.get(lvl, 0):
                    any_slots = True
                    line(box, f"Level {lvl} spell slots: {slots.get(lvl, 0)} of {maxs.get(lvl, 0)}")
            if not any_slots:
                line(box, "Spell slots: none yet")
            top = self.max_spell_level()
            line(box, f"Highest spell level you can cast: {top}"
                      + ("  (you can upcast anything into a bigger slot)" if top > 1 else ""),
                 style='Dim.TLabel')
        for label, flag in (("Second Wind", 'second_wind_available'),
                            ("Action Surge", 'action_surge_available'),
                            ("Sneak Attack", 'sneak_available'),
                            ("Class ability", 'class_resource_available')):
            if hasattr(self, flag) and (self.char_class in
                                        ('Fighter', 'Rogue') or flag == 'class_resource_available'):
                line(box, f"{label}: {'ready' if getattr(self, flag) else 'spent'}")

        # ----------------------------------------------------- active effects
        effects = []
        if getattr(self, 'haste_active', False):
            effects.append(f"Hasted ({self.haste_rounds} rounds left)")
        for flag, text in (('death_ward', 'Death Ward - the next killing blow leaves you at 1 HP'),
                           ('beacon_of_hope', 'Beacon of Hope - healing is doubled'),
                           ('escape_ready', 'A doorway is open - your next Flee succeeds'),
                           ('frost_armor', 'Armor of Agathys - attackers take cold damage'),
                           ('rage_active', 'Raging (+2 damage)'),
                           ('hunters_mark', "Hunter's Mark (+1d6 on hits)"),
                           ('hex_spell_active', 'Hex (+1d6 on hits)'),
                           ('guidance_ready', 'Guidance - +1d4 on your next check'),
                           ('wall_of_force', 'Wall of Force - nothing reaches you this round')):
            if getattr(self, flag, False):
                effects.append(text)
        for attr, text in (('bless_bonus', 'Bless (+%s to hit)'),
                           ('faith_bonus', 'Shield of Faith (+%s AC)'),
                           ('barkskin_dr', 'Barkskin (%s damage reduction)'),
                           ('whetstone_bonus', 'Honed weapon (+%s damage)'),
                           ('smite_charge', 'Smite charged (+%sd8 on your next hit)'),
                           ('extra_shots', 'Swift Quiver (+%s shots per attack)'),
                           ('lucky_bonus', 'Lucky coin (+%s on your next roll)'),
                           ('spirit_weapon', 'Spiritual Weapon (%sd8 each round)'),
                           ('check_bonus_temp', 'Enhance Ability (+%s to checks)')):
            value = getattr(self, attr, 0)
            if value:
                effects.append(text % value)
        if getattr(self, 'poison_weapon', 0):
            effects.append('Poisoned blade (+1d6 poison on hits)')
        if getattr(self, 'radiant_weapon', 0):
            effects.append('Blessed blade (+1d6 radiant on hits)')
        if getattr(self, 'poisoned', 0):
            effects.append(f"POISONED - {self.poisoned} more rounds of damage")
        if getattr(self, 'cursed_rounds', 0):
            effects.append(f"CURSED - -3 to your attacks for {self.cursed_rounds} more rounds")
        if getattr(self, 'entangled', 0):
            effects.append(f"Stuck fast - no bonus action for {self.entangled} more rounds")
        box = section("Active Effects")
        if effects:
            for text in effects:
                line(box, "\u2022 " + text)
        else:
            line(box, "Nothing active right now.", style='Dim.TLabel')

        # --------------------------------------------------------- the bag
        box = section("Inventory")
        stacks = self.inventory_stacks()
        if stacks:
            for item, count in stacks:
                label = item if count == 1 else f"{item}  x{count}"
                if item in MAGIC_ITEMS:
                    label += f"   [{MAGIC_ITEMS[item]['rarity']}]"
                line(box, label)
        else:
            line(box, "(empty)", style='Dim.TLabel')


    def show_help(self):
        """Print the controls and the rules that are easy to miss into the log."""
        self.log_message("Explore opens the dungeon: move room to room with the arrow keys or WASD. "
                         "Walking into an enemy room starts the fight immediately \u2014 there is no "
                         "confirmation step, so keep an eye on your HP. Spring or disarm traps (^), loot "
                         "chests (#), trade at shops (S), rest at camps (C), and find the stairs (v).")
        self.log_message("BOSSES (B) guard the stairs every third floor. They hit several times a round, "
                         "have a signature move on a cooldown, and get angrier below half health. Press "
                         "Bonus Action \u2192 Size Up the Enemy to learn what a boss resists before you "
                         "commit. Beating it opens the stairs down.", color='important')
        self.log_message("FLEEING: the Flee button is available every round of every fight. It is a "
                         "Dexterity check \u2014 harder with more enemies, deeper floors and bosses. Win "
                         "and you fall back to the room you came from with the enemies still there. Lose "
                         "and they get a free round. Smoke bombs, cloaks and boots help; Misty Step and "
                         "Dimension Door make it automatic. If everything is at range you get a head "
                         "start.", color='important')
        self.log_message("RANGE & COVER: some enemies fight from a distance ('at range' on their card). "
                         "Melee swings close in on them automatically using your free move for the "
                         "round; ranged weapons and spells reach them where they stand. The Move button "
                         "spends that move on purpose: Close In without swinging, Fall Back from a pack "
                         "(they get a parting swipe \u2014 unless you are a Rogue), or Take Cover behind "
                         "whatever the room offers for +2 AC against shots and half damage from a boss's "
                         "breath or quake. Watch for bosses winding up \u2014 they always show it one "
                         "round early.", color='important')
        self.log_message("COMPANIONS: any shop will hire you one ally \u2014 a sellsword who draws "
                         "attacks, an archer, an apprentice, or a field medic. They act after you end "
                         "your turn, scale with your level, and are gone for good at 0 HP. Enemies are "
                         "smarter now too: they gang up, hurt skirmishers fall back behind cover, and a "
                         "broken pack's survivors may simply run.", color='important')
        self.log_message("Your turn: attacking only spends your ACTION. You keep your BONUS ACTION "
                         "(off-hand strike, defend, sizing up a foe, using an item) until you press End "
                         "Turn \u2014 nothing happens on the enemies' side until you do.", color='important')
        self.log_message("GEAR: press Gear to see all four equipment slots (weapon, armour, shield, "
                         "trinket), what each one is doing for you, and everything in your bag that could "
                         "go there instead. Stats shows the same thing plus your Hit Dice, spell slots and "
                         "every active effect. Stats, Spells and Gear are tabs of one window now "
                         "\u2014 flip between them at the top.")
        self.log_message("Items: select one in the Inventory list to read what it does. Using an item in "
                         "combat costs your bonus action; swapping gear costs your action. Tools like "
                         "thieves tools, a crowbar and climbing gear work from inside your bag (+3 to the "
                         "relevant checks) without being used up.")
        self.log_message("Spells: press Spells to open your spellbook at any time. Leveled spells show one "
                         "button per slot you could spend \u2014 UPCASTING into a bigger slot makes the "
                         "spell stronger. Cantrips are free and gain extra dice at levels 5, 11 and 17. "
                         "Out of combat only utility and healing spells will work.", color='important')
        self.log_message("Resting: a Short Rest spends one Hit Die to heal (your remaining Hit Dice are "
                         "shown in the character panel and on the Stats screen). A Long Rest needs a camp "
                         "and restores everything, Hit Dice and spell slots included.")
        self.log_message("Levelling: you gain an Ability Score Improvement at levels 4, 8, 12, 16 and 19 "
                         "\u2014 +2 to one ability or +1 to two.")
        self.log_message("Music: drag the Music slider at the top, or press - and + at any time.")
