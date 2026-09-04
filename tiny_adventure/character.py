"""Characters: creation, classes, ability scores, derived stats, and levelling.

A character is built in one of two ways, and both end in apply_class():

    open_character_creator()   the full dialog - roll stats, assign them by
                               hand, pick a class, level and spells
    quick_start_class()        rolls everything automatically using
                               CLASS_STAT_PRIORITY from data.py

apply_class() is the single place that turns "I am a level 3 Cleric" into
actual gear, spell slots, known spells and resources. If a new character is
ever missing something, that is the method to look at.

DERIVED STATS
Your AC, attack bonus, damage and max HP are never stored as truth - they are
recomputed from your abilities and gear by update_derived_stats(). Call it
after changing anything that feeds them. This is deliberate: it means a stat
can never drift out of sync with the equipment causing it.

ABILITY SCORES AND GEAR
self.strength and friends hold your *base* score. Magic items add to that,
so nothing reads those attributes directly for a roll - it goes through:

    ability_score('strength')   base + every magic item bonus
    ability_mod('strength')     the modifier of that total

Use those two anywhere a score actually matters. Reading self.strength gives
you the number on your character sheet before the gauntlets.

ABILITY SCORE IMPROVEMENTS
Hitting one of ASI_LEVELS (4, 8, 12, 16, 19) opens open_asi_dialog: either +2
to one ability or +1 to two, capped at ABILITY_CAP. This raises the BASE
score, so it stacks with gear.

SPELL BUDGETS
How many spells you know is worked out, not stored:

    spell_budget(class, level)   how many cantrips and spells you should know
    max_spell_level(...)         the highest spell level you can cast
    compute_slots(...)           how many slots of each level you get
    class_spell_list(...)        which spells your class may learn at all

Those four drive the creator, the level-up chooser and the spellbook alike, so
changing one changes the whole game consistently.

WHERE TO CHANGE THINGS

    Max HP formula ................ update_derived_stats
    XP needed per level ........... add_xp / level_up (the XP_GROWTH curve)
    Spell slots per level ......... compute_slots
    How many spells you know ...... spell_budget
    What you start with ........... apply_class, and STARTING_KIT in data.py
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (WEAPONS, FINESSE, ARMOR, SHIELDS, MAGIC_ITEMS, EQUIP_SLOTS,
                   SLOT_ATTR, CLASSES, SUBCLASSES, DIFFICULTIES, CLASS_SPELLS,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, SPELL_CATALOG, SPELL_LEVELS, ASI_LEVELS,
                   ABILITY_CAP, MAX_CHARACTER_LEVEL, MAX_START_LEVEL,
                   PLAYER_HP_BASE, XP_GROWTH)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class CharacterMixin:

    QUICK_NAMES = ["Adventurer", "Bramble", "Kestrel", "Orin", "Sable", "Thorne",
                   "Vesper", "Wren", "Cass", "Dain", "Nyx", "Rooke"]

    def apply_class(self, class_name, level=1, chosen_spells=None, subclass=None):
        """Turn a bare character into a level-N member of `class_name`.

        Applies ability bonuses, gear, the starting kit, spell slots, class
        resources and a subclass. This is the one place a character's class is set
        up, so both the creator and Quick Start end up identical.

        chosen_spells: the player's own picks. If None, a sensible class-appropriate
        loadout is rolled instead. Either way the result is filtered to the class
        list, so an illegal spell can never sneak in.

        subclass: the character's path within the class. If None (or not one of
        this class's paths in SUBCLASSES), one is chosen at random - every
        adventurer walks some path.
        
"""
        info = CLASSES.get(class_name, CLASSES['Fighter'])
        self.char_class = class_name
        subs = SUBCLASSES.get(class_name, {})
        if subclass not in subs:
            subclass = random.choice(list(subs)) if subs else None
        self.subclass = subclass
        for stat, bonus in info['stat_bonus'].items():
            setattr(self, stat, getattr(self, stat) + bonus)
        self.class_hit_die = info['hit_die']
        self.cast_stat = info['cast_stat']
        self.caster_type = info['caster']
        self.equipped_weapon = info['weapon']
        self.equipped_armor = info['armor']
        self.equipped_shield = info.get('shield')
        self.equipped_trinket = None
        # everyone packs a basic kit, plus whatever their class brings along,
        # plus a few extra supplies if they are starting as a veteran
        for it in STARTING_KIT:
            self.inventory.append(it)
        for it in info['extra_items']:
            self.inventory.append(it)
        for _ in range(level - 1):
            self.inventory.append('potion')

        # spell slots by caster type
        self.spell_slots_max_by_level = self.compute_slots(info['caster'], level)
        for lvl in SPELL_LEVELS:
            self.spell_slots_max_by_level.setdefault(lvl, 0)
        self.spell_slots_by_level = dict(self.spell_slots_max_by_level)
        # Hit Dice: number available on short rests and a max for display/restore
        self.hit_dice = level
        self.hit_dice_max = level
        # known spells: the player's picks if they made any, otherwise a sensible
        # random loadout. Either way everything is filtered to the class list.
        if chosen_spells:
            legal = self.class_spell_list(class_name, max_level=self.max_spell_level(info['caster'], level))
            self.known_spells = [k for k in chosen_spells if k in legal]
        else:
            self.known_spells = self.auto_pick_spells(class_name, level)

        # progression: starting above level 1 walks the XP curve forward
        self.player_level = level
        self.xp = 0
        self.xp_to_next = 100
        for _ in range(level - 1):
            # Each level needs XP_GROWTH times the last (data.py). Lower it for
            # faster levelling, raise it for a longer game.
            self.xp_to_next = int(self.xp_to_next * XP_GROWTH)
        self.hit_dice = level
        self.gold += 30 * (level - 1)  # veterans start better funded

        # class resources
        self.second_wind_available = class_name == 'Fighter'
        self.action_surge_available = class_name == 'Fighter'
        self.sneak_available = class_name == 'Rogue'
        self.class_resource_available = True
        self.hunters_mark = False
        self.hex_active = False
        self.rage_active = False
        self.smite_charge = 0
        self.asi_pending = 0
        self.temp_hp = 0

        self.character_created = True
        self.update_derived_stats()
        self.health = self.max_health

    def subclass_effects(self):
        """Everything your subclass grants, in gear_effects() key form.

        Returns {} for no class or no subclass, so it is always safe to call.
        The one subclass-only key, max_hp_per_level, is multiplied out into a
        flat max_hp here so gear_effects can merge it like any other bonus.
        
"""
        info = SUBCLASSES.get(getattr(self, 'char_class', None) or '', {}) \
                         .get(getattr(self, 'subclass', None) or '')
        if not info:
            return {}
        fx = {k: v for k, v in info.items() if k not in ('desc', 'max_hp_per_level')}
        per = info.get('max_hp_per_level', 0)
        if per:
            fx['max_hp'] = fx.get('max_hp', 0) + per * max(1, getattr(self, 'player_level', 1))
        return fx

    def quick_start_class(self, class_name, level=1, subclass=None):
        """Build a complete random character in one go, ready to play.

        Rolls a real 4d6-drop-lowest array and assigns the best scores to whatever
        that class cares about, then hands off to apply_class for gear and spells.
        The result is the same quality as a hand-built character.
        
"""
        self.reset_game()
        # prefer typed name if present, otherwise pick one at random
        typed_name = self.name_entry.get().strip()
        self.name = typed_name or random.choice(self.QUICK_NAMES)
        # roll a real 4d6-drop-lowest array and drop the best scores where this
        # class wants them, exactly like a hand-built character would
        rolls = self.roll_stat_array()
        priority = CLASS_STAT_PRIORITY.get(class_name, CLASS_STAT_PRIORITY['Fighter'])
        for stat, value in zip(priority, rolls):
            setattr(self, stat, value)
        self.endurance = self.roll_ability_score()
        self.apply_class(class_name, level=level, subclass=subclass)
        self.log_message(
            f"Rolled {', '.join(str(r) for r in rolls)} (4d6 drop lowest) and assigned them "
            f"to a {class_name}'s best abilities.", color='important')
        # mark first run done for convenience
        try:
            root_dir = game_dir()
            flag = os.path.join(root_dir, '.tiny_adventure_first_run')
            with open(flag, 'w') as f:
                f.write('quickstart')
        except Exception:
            pass
        self.update_derived_stats()
        self.health = self.max_health
        self.gold = 10 + 30 * (level - 1)
        path = f"{self.subclass} " if getattr(self, 'subclass', None) else ""
        self.log_message(f"Quick Start: Welcome, {self.name} the {path}{self.char_class} (level {level})!")
        if self.known_spells:
            names = ', '.join(self.spell_catalog[k][0] for k in self.known_spells
                              if k in self.spell_catalog)
            self.log_message(f"You have prepared: {names}.", color='important')
        self.refresh_stats()
        self.refresh_inventory()
        self.refresh_buttons()
        # trigger an immediate autosave and start periodic autosave
        try:
            self.save_quick(self.quick_save_path)
        except Exception:
            pass
        self.start_autosave()

    def start_game(self):
        # Capture any name typed in before resetting, then open creator with it
        """Start over: wipe the character and open the creator."""
        typed_name = self.name_entry.get().strip()
        self.reset_game()
        self.open_character_creator(prefill_name=typed_name)

    def reset_game(self):
        """Wipe everything back to a blank slate for a new character.

        Also re-reads settings and rebuilds the save paths, so it is the safe way to
        start over without restarting the program.
        
"""
        self.gold = 10
        self.inventory = []
        self.name = "Adventurer"
        self.randomize_abilities()
        self.in_combat = False
        self.enemies = []
        self.target_index = 0
        self.combat_round = 0
        self.player_ac = 13
        self.player_attack_bonus = 2
        self.player_damage_dice = 6
        self.player_damage_bonus = 1
        self.enemy_attack_pending = False
        self.shop_available = False
        self.current_event = None
        self.pending_enemies = []
        self.torch_active = False
        self.lantern_active = False
        self.can_long_rest = False
        # wipe class/progression state so a new character starts clean
        self.player_level = 1
        self.xp = 0
        self.xp_to_next = 100
        self.known_spells = []
        self.spell_slots_by_level = {lvl: 0 for lvl in SPELL_LEVELS}
        self.spell_slots_max_by_level = {lvl: 0 for lvl in SPELL_LEVELS}
        self.sneak_available = False
        self.sneak_active = False
        self.second_wind_available = False
        self.action_surge_available = False
        self.equipped_weapon = None
        self.equipped_armor = None
        self.equipped_shield = None
        self.equipped_trinket = None
        self.hit_dice = 1
        self.class_hit_die = 8
        self.hit_dice_max = 1
        self.cast_stat = None
        self.caster_type = None
        self.class_resource_available = True
        self.rage_active = False
        self.hunters_mark = False
        self.hex_active = False
        self.smite_charge = 0
        self.true_strike_bonus = 0
        self.haste_active = False
        self.haste_rounds = 0
        self.extra_action_available = False
        self.mage_hand_ready = False
        self.illusion_lure = False
        self.levitate_charge = False
        self.asi_pending = 0
        self.temp_hp = 0
        self.poisoned = 0
        self.aid_bonus = 0
        self.death_ward = False
        self.escape_ready = False
        self.guidance_ready = False
        self.lucky_bonus = 0
        self.damage_reduction = 0
        # the companion and the adaptive dial belong to a run, not the app
        self.companion = None
        self.adaptive_mult = 1.0
        self.recent_fights = []
        self.clear_combat_effects()
        self.player_action_available = True
        self.player_bonus_available = True
        self.hide_combat_panel()
        self.dungeon = None  # regenerated on first Explore
        self.close_dungeon_window()
        # save/load support
        self.save_folder = os.path.join(game_dir(), 'saves')
        try:
            os.makedirs(self.save_folder, exist_ok=True)
        except Exception:
            pass
        self.quick_save_path = os.path.join(self.save_folder, 'quicksave.json')
        self.autosave_path = os.path.join(self.save_folder, 'autosave.json')
        self.settings_path = os.path.join(self.save_folder, 'settings.json')
        # load settings if present
        try:
            self.load_settings()
        except Exception:
            # ensure defaults
            pass
        self.update_derived_stats()
        self.health = self.max_health
        self.name_entry.delete(0, tk.END)
        # Do not auto-fill the name entry; character not created until Start pressed
        self.character_created = False
        self.char_class = None
        self.subclass = None
        self.refresh_stats()
        self.refresh_inventory()
        self.refresh_buttons()

    def open_character_creator(self, prefill_name=None):
        # Character creation dialog resembling D&D rolling
        """The full character creation dialog, now a single window.

        Roll 4d6-drop-lowest, place the six numbers on your abilities, choose a
        class and starting level, and - for casters - tick your spells right
        here (the spell list used to be a second window that could open off the
        bottom of the screen). The whole dialog scrolls and clamps itself to
        the screen, so nothing can open out of reach.

        Placing numbers is forgiving: assigning onto a filled ability frees
        its old roll back to the pool, and clicking a placed number picks it
        straight back up - a misclick costs one click, not a re-roll.
        
"""
        creator = self.make_popup("Character Creation")
        content = self.make_scrollable(creator)
        frame = ttk.Frame(content, padding=(14, 12))
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Create Your Character", style='Gold.TLabel',
                  font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)

        name_row = ttk.Frame(frame)
        name_row.pack(fill=tk.X, pady=(8, 6))
        ttk.Label(name_row, text="Name:").pack(side=tk.LEFT)
        name_entry = ttk.Entry(name_row, width=28)
        name_entry.pack(side=tk.LEFT, padx=(6, 0))
        if prefill_name:
            name_entry.insert(0, prefill_name)

        class_row = ttk.Frame(frame)
        class_row.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(class_row, text="Class:").pack(side=tk.LEFT)
        class_combo = ttk.Combobox(class_row, values=list(CLASSES.keys()),
                                   state="readonly", width=18)
        class_combo.pack(side=tk.LEFT, padx=(6, 0))
        class_combo.set("Fighter")
        ttk.Label(class_row, text="  Start at level:").pack(side=tk.LEFT)
        level_spin = ttk.Spinbox(class_row, from_=1, to=MAX_START_LEVEL, width=4)
        level_spin.set(1)
        level_spin.pack(side=tk.LEFT, padx=(4, 0))

        # every class walks one of two paths (its D&D-style subclass)
        path_row = ttk.Frame(frame)
        path_row.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(path_row, text="Path:").pack(side=tk.LEFT)
        path_combo = ttk.Combobox(path_row, state="readonly", width=24)
        path_combo.pack(side=tk.LEFT, padx=(11, 0))
        path_desc = ttk.Label(frame, text="", style='Dim.TLabel', wraplength=540,
                              justify=tk.LEFT)
        path_desc.pack(anchor=tk.W, pady=(2, 2))

        def refresh_path_desc(event=None):
            cls = class_combo.get() or "Fighter"
            info = SUBCLASSES.get(cls, {}).get(path_combo.get(), {})
            path_desc.configure(text=info.get('desc', ''))

        def refresh_paths():
            cls = class_combo.get() or "Fighter"
            names = list(SUBCLASSES.get(cls, {}))
            path_combo.configure(values=names)
            if names:
                path_combo.set(names[0])
            else:
                path_combo.set('')
            refresh_path_desc()

        path_combo.bind('<<ComboboxSelected>>', refresh_path_desc)

        hint = ttk.Label(frame, text="", style='Dim.TLabel', wraplength=540,
                         justify=tk.LEFT)
        hint.pack(anchor=tk.W, pady=(2, 4))

        # ----------------------------------------------------- ability scores
        stats_frame = ttk.LabelFrame(frame, text="Ability Scores (4d6 drop lowest)",
                                     padding=8)
        stats_frame.pack(fill=tk.X, pady=(6, 6))

        stat_names = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
        stat_vars = {}

        creator.roll_buttons = []      # [(pool button, value)]
        creator.selected_roll = None   # (pool button, value) currently picked up
        creator.assigned = {}          # stat -> value
        creator.assigned_btn = {}      # stat -> the pool button that value came from
        creator.selected_spells = []

        for s in stat_names:
            row = ttk.Frame(stats_frame)
            row.pack(fill=tk.X, pady=(2, 2))
            ttk.Label(row, text=f"{s}:", width=6).pack(side=tk.LEFT)
            val_btn = ttk.Button(row, text='-', width=6,
                                 command=lambda stat=s: unassign_stat(stat))
            val_btn.pack(side=tk.LEFT)
            assign_btn = ttk.Button(row, text="Assign", width=8,
                                    command=lambda stat=s: assign_to_stat(stat))
            assign_btn.pack(side=tk.LEFT, padx=(6, 0))
            stat_vars[s] = (val_btn, assign_btn)

        pool_box = ttk.LabelFrame(frame, text="Rolled Pool", padding=8)
        pool_box.pack(fill=tk.X, pady=(2, 6))
        pool_row = ttk.Frame(pool_box)
        pool_row.pack(fill=tk.X)
        # Reroll / Clear sit right here, under the numbers they act on, where
        # they can be seen and clicked - not at the bottom of the dialog below
        # a spell list that can run past the edge of the screen. The row is
        # made now so it packs above the status line; the buttons are added a
        # little further down, once the functions they call exist.
        pool_btn_row = ttk.Frame(pool_box)
        pool_btn_row.pack(fill=tk.X, pady=(6, 2))
        status = ttk.Label(pool_box, text="", style='Dim.TLabel', wraplength=540,
                           justify=tk.LEFT)
        status.pack(anchor=tk.W, pady=(6, 0))

        def set_status(text):
            try:
                status.configure(text=text)
            except Exception:
                pass

        def refresh_pool_states():
            used = set(creator.assigned_btn.values())
            for b, _v in creator.roll_buttons:
                try:
                    b.state(['disabled'] if b in used else ['!disabled'])
                    picked = (creator.selected_roll is not None
                              and creator.selected_roll[0] is b)
                    b.state(['pressed'] if picked else ['!pressed'])
                except Exception:
                    pass

        def update_progress():
            done = len(creator.assigned)
            if done < len(stat_names):
                set_status(f"Assigned {done} of {len(stat_names)}. Click a number, then Assign. "
                           "Click a placed number to take it back.")
            else:
                set_status("All six assigned. Misclicked one? Click the placed number to move it.")

        def select_roll(btn, value):
            if any(btn is b for b in creator.assigned_btn.values()):
                set_status("That number is already placed - click it on its ability to take it back.")
                return
            creator.selected_roll = (btn, value)
            refresh_pool_states()
            set_status(f"Picked up {value} - press Assign next to the ability it belongs on.")

        def assign_to_stat(stat):
            if not creator.selected_roll:
                set_status("Pick a number from the rolled pool first, then press Assign.")
                return
            btn, val = creator.selected_roll
            # assigning onto a filled ability frees its old roll back to the pool
            creator.assigned_btn.pop(stat, None)
            creator.assigned[stat] = val
            creator.assigned_btn[stat] = btn
            stat_vars[stat][0].configure(text=str(val))
            creator.selected_roll = None
            refresh_pool_states()
            update_progress()

        def unassign_stat(stat):
            # clicking a placed number takes it back and picks it up again
            btn = creator.assigned_btn.pop(stat, None)
            val = creator.assigned.pop(stat, None)
            if btn is None and val is None:
                set_status("Nothing placed there yet - pick a number from the pool below.")
                return
            stat_vars[stat][0].configure(text='-')
            if btn is not None and val is not None:
                creator.selected_roll = (btn, val)
                set_status(f"Took back {val} - press Assign next to where it should go.")
            refresh_pool_states()

        def clear_assignments():
            creator.assigned.clear()
            creator.assigned_btn.clear()
            creator.selected_roll = None
            for s in stat_names:
                stat_vars[s][0].configure(text='-')
            refresh_pool_states()
            set_status("Assignments cleared - the same rolls are still yours to place.")

        def roll_stats_for_creator():
            # generate 6 roll values (4d6 drop lowest), best first
            for w in pool_row.winfo_children():
                w.destroy()
            creator.roll_buttons = []
            rolls = sorted((self.roll_ability_score() for _ in range(6)), reverse=True)
            for v in rolls:
                b = ttk.Button(pool_row, text=str(v), width=5)
                b.pack(side=tk.LEFT, padx=(0, 6), pady=(0, 2))
                b.configure(command=lambda btn=b, val=v: select_roll(btn, val))
                creator.roll_buttons.append((b, v))
            clear_assignments()
            update_progress()

        def creator_level():
            try:
                return max(1, min(MAX_START_LEVEL, int(level_spin.get())))
            except Exception:
                return 1

        # the buttons for the pool, into the row reserved for them above -
        # created here because the commands they call are only just defined
        ttk.Button(pool_btn_row, text="Reroll Stats",
                   command=roll_stats_for_creator).pack(side=tk.LEFT)
        ttk.Button(pool_btn_row, text="Clear Assignments",
                   command=clear_assignments).pack(side=tk.LEFT, padx=(8, 0))

        # ------------------------------------------------------------- spells
        # casters pick their spells right here instead of in a second window
        spells_box = ttk.LabelFrame(frame, text="Spells", padding=8)
        spells_box.pack(fill=tk.X, pady=(2, 6))
        _abbr = {'strength': 'STR', 'dexterity': 'DEX', 'constitution': 'CON',
                 'intelligence': 'INT', 'wisdom': 'WIS', 'charisma': 'CHA'}

        def refresh_spell_section(event=None):
            refresh_paths()
            for w in spells_box.winfo_children():
                w.destroy()
            # picks from a different class/level no longer apply
            creator.selected_spells = []
            cls = class_combo.get() or "Fighter"
            level = creator_level()
            prio = (CLASS_STAT_PRIORITY.get(cls) or [None])[0]
            hint.configure(text=(f"A {cls} leans on {_abbr.get(prio, '')} - "
                                 "give it your best roll.") if prio in _abbr else "")
            caster = CLASSES.get(cls, {}).get('caster')
            if not caster:
                ttk.Label(spells_box, text=f"A {cls} does not cast spells - nothing to pick here.",
                          style='Dim.TLabel').pack(anchor=tk.W)
                return
            cantrip_budget, leveled_budget = self.spell_budget(cls, level)
            top = self.max_spell_level(caster, level)
            ttk.Label(spells_box,
                      text=f"A level {level} {cls} knows {cantrip_budget} cantrip(s) and "
                           f"{leveled_budget} spell(s), up to spell level {top}. "
                           "Tick yours below, or let Pick For Me choose.",
                      style='Dim.TLabel', wraplength=540, justify=tk.LEFT).pack(anchor=tk.W)

            cantrip_vars = {}
            leveled_vars = {}
            info = ttk.Label(spells_box, text="", style='Gold.TLabel')

            def counts():
                return (sum(1 for v, _c in cantrip_vars.values() if v.get()),
                        sum(1 for v, _c in leveled_vars.values() if v.get()))

            def update_count(*_):
                c, l = counts()
                info.configure(text=f"Cantrips {c}/{cantrip_budget}   Spells {l}/{leveled_budget}")
                # grey out the unpicked boxes once a budget is full
                for group, used_n, budget in ((cantrip_vars, c, cantrip_budget),
                                              (leveled_vars, l, leveled_budget)):
                    for var, cb in group.values():
                        try:
                            cb.state(['disabled'] if (used_n >= budget and not var.get())
                                     else ['!disabled'])
                        except Exception:
                            pass
                creator.selected_spells = (
                    [k for k, (v, _c) in cantrip_vars.items() if v.get()]
                    + [k for k, (v, _c) in leveled_vars.items() if v.get()])

            for lvl in range(0, top + 1):
                keys = [k for k in self.class_spell_list(cls, max_level=top)
                        if self.spell_catalog[k][2] == lvl]
                if not keys:
                    continue
                title = (f"Cantrips (choose {cantrip_budget})" if lvl == 0
                         else f"Level {lvl} spells")
                box = ttk.LabelFrame(spells_box, text=title, padding=6)
                box.pack(fill=tk.X, pady=(4, 2))
                for key in keys:
                    name, desc, _l, action = self.spell_catalog[key]
                    var = tk.BooleanVar(value=False)
                    cb = ttk.Checkbutton(box, text=f"{name} \u2014 {desc} [{action}]", variable=var)
                    cb.pack(anchor=tk.W)
                    var.trace_add('write', update_count)
                    (cantrip_vars if lvl == 0 else leveled_vars)[key] = (var, cb)

            def randomize():
                picks = self.auto_pick_spells(cls, level)
                for group in (cantrip_vars, leveled_vars):
                    for key, (var, _cb) in group.items():
                        var.set(key in picks)

            row = ttk.Frame(spells_box)
            row.pack(fill=tk.X, pady=(6, 0))
            ttk.Button(row, text="Pick For Me", command=randomize).pack(side=tk.LEFT)
            info.pack(anchor=tk.W, pady=(4, 0))
            update_count()

        class_combo.bind('<<ComboboxSelected>>', refresh_spell_section)
        level_spin.configure(command=refresh_spell_section)
        level_spin.bind('<KeyRelease>', refresh_spell_section)

        def finalize():
            # ensure assignments exist
            assigned = creator.assigned
            if not assigned or len(assigned) < len(stat_names):
                set_status("Assign a rolled value to every ability before finalizing.")
                self.log_message("Assign a rolled value to each ability before finalizing.")
                return
            # apply rolled scores to character
            self.strength = assigned["STR"]
            self.dexterity = assigned["DEX"]
            self.constitution = assigned["CON"]
            self.intelligence = assigned["INT"]
            self.wisdom = assigned["WIS"]
            self.charisma = assigned["CHA"]
            # apply chosen class bonuses
            selected = class_combo.get() or "Fighter"
            start_level = creator_level()
            # the player's own spell picks win; if they skipped the boxes we
            # roll them a sensible class-appropriate loadout instead
            picked = creator.selected_spells or None
            self.apply_class(selected, level=start_level, chosen_spells=picked,
                             subclass=path_combo.get() or None)
            # Read the name the player typed in the creator (fall back to a default)
            self.name = name_entry.get().strip() or "Adventurer"
            self.gold = 10 + 30 * (start_level - 1)
            creator.destroy()
            # mark first run complete by creating a small flag file next to the script
            try:
                root_dir = game_dir()
                flag = os.path.join(root_dir, '.tiny_adventure_first_run')
                with open(flag, 'w') as f:
                    f.write('created')
            except Exception:
                pass
            self.refresh_stats()
            self.refresh_inventory()
            self.refresh_buttons()
            path = f"{self.subclass} " if getattr(self, 'subclass', None) else ""
            self.log_message(f"Welcome, {self.name} the {path}{self.char_class}!")
            if self.known_spells:
                names = ', '.join(self.spell_catalog[k][0] for k in self.known_spells
                                  if k in self.spell_catalog)
                self.log_message(f"You have prepared: {names}.", color='important')
            self.log_message("You wake up in a tiny room with a backpack and a suspiciously shiny key.")
            # save and start autosave
            try:
                self.save_quick(self.quick_save_path)
            except Exception:
                pass
            self.start_autosave()

        ttk.Button(frame, text="Finalize Character", command=finalize).pack(pady=(8, 2))

        # a pool is ready the moment the window opens; re-roll freely
        roll_stats_for_creator()
        refresh_spell_section()
        self.place_window(creator, min_w=600, min_h=540)

    def ability_modifier(self, score):
        """Convert an ability score into its modifier: 10-11 gives +0, 18 gives +4.

        The standard D&D formula. Used everywhere a score affects a roll.
        
"""
        return (score - 10) // 2

    def ability_score(self, name):
        """Your total score in one ability: the base you rolled plus every gear bonus.

        This is the number that should decide a roll. self.strength on its own is
        just the base, which is why nothing in the game reads it directly.
        
"""
        base = getattr(self, name, 10)
        return base + self.gear_effects().get('stat', {}).get(name, 0)

    def ability_mod(self, name):
        """The modifier for one ability, gear included. The usual way to get a modifier."""
        return self.ability_modifier(self.ability_score(name))

    def cantrip_dice(self):
        """How many damage dice your cantrips roll - it grows with your level, not with slots.

        One die to start, two at level 5, three at 11, four at 17. This is what keeps
        a cantrip worth casting at high level.
        
"""
        lvl = getattr(self, 'player_level', 1)
        return 1 + (lvl >= 5) + (lvl >= 11) + (lvl >= 17)

    def compute_wizard_slots(self, level):
        """Spell slot maxima for a full caster (Wizard, Cleric, Bard, Druid, Sorcerer).

        The familiar full-caster table, running to character level 20. The game only
        tracks slots up to level 5, so the 6th-level-and-up rows are simply left off
        rather than being crammed into level 5.
        
"""
        table = {
            1:  {1: 2},
            2:  {1: 3},
            3:  {1: 4, 2: 2},
            4:  {1: 4, 2: 3},
            5:  {1: 4, 2: 3, 3: 2},
            6:  {1: 4, 2: 3, 3: 3},
            7:  {1: 4, 2: 3, 3: 3, 4: 1},
            8:  {1: 4, 2: 3, 3: 3, 4: 2},
            9:  {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
            10: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
            11: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
            12: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
            13: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
            14: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
            15: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
            16: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
            17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3},
            18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3},
            19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3},
            20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3},
        }
        lvl = max(1, min(level, max(table.keys())))
        return dict(table[lvl])

    def compute_slots(self, caster_type, level):
        """Spell slot maxima for any caster type at a given character level.

            'full'  Wizard/Cleric/Bard/Sorcerer/Druid - the standard table
            'half'  Paladin/Ranger - slower, fewer, and they top out lower
            'pact'  Warlock - only a couple, but always at the highest level
            None    no spellcasting

        Every returned dict is padded out across SPELL_LEVELS so callers never have
        to guard against a missing key.
        
"""
        if caster_type == 'full':
            slots = self.compute_wizard_slots(level)
        elif caster_type == 'half':
            # half casters (Paladin, Ranger) come online slowly and stop early
            if level < 2:
                slots = {1: 1}
            elif level < 5:
                slots = {1: 2}
            elif level < 9:
                slots = {1: 4, 2: 2}
            elif level < 13:
                slots = {1: 4, 2: 3, 3: 2}
            elif level < 17:
                slots = {1: 4, 2: 3, 3: 3, 4: 1}
            else:
                slots = {1: 4, 2: 3, 3: 3, 4: 2, 5: 1}
        elif caster_type == 'pact':
            # warlocks get few slots, but always at their highest level
            top = 1 if level < 3 else (2 if level < 5 else
                                       (3 if level < 7 else (4 if level < 9 else 5)))
            count = 2 if level < 11 else (3 if level < 17 else 4)
            slots = {top: count}
        else:
            slots = {}
        return {lvl: slots.get(lvl, 0) for lvl in SPELL_LEVELS}

    def max_spell_level(self, caster_type=None, level=None):
        """Highest spell level this character can cast (0 = cantrips only)."""
        caster_type = caster_type if caster_type is not None else getattr(self, 'caster_type', None)
        level = level if level is not None else getattr(self, 'player_level', 1)
        slots = self.compute_slots(caster_type, level)
        top = 0
        for lvl in sorted(slots):
            if slots.get(lvl, 0) > 0:
                top = lvl
        return top

    def spell_budget(self, class_name, level):
        """How many cantrips and leveled spells this class knows at `level`."""
        caster = CLASSES.get(class_name, {}).get('caster')
        if caster == 'full':
            cantrips = 2 + (1 if level >= 4 else 0) + (1 if level >= 10 else 0)
            leveled = level + 2
        elif caster == 'pact':
            cantrips = 2 + (1 if level >= 4 else 0) + (1 if level >= 10 else 0)
            leveled = min(level + 1, 15)
        elif caster == 'half':
            cantrips = 0
            leveled = max(1, (level + 1) // 2 + 2)
        else:
            return 0, 0
        return cantrips, leveled

    def class_spell_list(self, class_name=None, max_level=None, include_cantrips=True):
        """Every spell `class_name` may know, optionally capped at a spell level."""
        class_name = class_name or getattr(self, 'char_class', None)
        allowed = CLASS_SPELLS.get(class_name, [])
        out = []
        for key in allowed:
            entry = self.spell_catalog.get(key)
            if not entry:
                continue
            lvl = entry[2]
            if lvl == 0 and not include_cantrips:
                continue
            if max_level is not None and lvl > max_level:
                continue
            out.append(key)
        return out

    def can_cast_now(self, spell_key, slot_level=None):
        """(bool, reason) for whether this spell can be cast right now.

        slot_level lets you ask about upcasting: can_cast_now('fireball', 5) checks
        whether you have a 5th-level slot free, not a 3rd. Leave it out to ask about
        the spell's own level.
        
"""
        entry = self.spell_catalog.get(spell_key)
        if not entry:
            return False, "You don't know that spell."
        _name, _desc, lvl, _action = entry
        slot_level = lvl if slot_level is None else slot_level
        if spell_key not in self.class_spell_list():
            return False, f"A {getattr(self, 'char_class', 'character')} cannot cast that."
        if lvl > 0 and spell_key not in getattr(self, 'known_spells', []):
            return False, "You don't know that spell."
        if slot_level < lvl:
            return False, f"{_name} needs at least a level {lvl} slot."
        if not self.in_combat and spell_key not in OUT_OF_COMBAT_SPELLS:
            return False, "There is no one to use that on right now."
        if slot_level > 0 and self.spell_slots_by_level.get(slot_level, 0) <= 0:
            return False, f"No level {slot_level} slots left."
        return True, ""

    def castable_slot_levels(self, spell_key):
        """Every slot level this spell could be cast from right now, lowest first.

        A cantrip returns [0]. A level 1 spell with a level 3 slot free returns
        [1, 3] and so on - which is exactly what the spellbook needs to draw its
        row of upcast buttons.
        
"""
        entry = self.spell_catalog.get(spell_key)
        if not entry:
            return []
        base = entry[2]
        if base == 0:
            return [0]
        top = self.max_spell_level()
        return [lvl for lvl in SPELL_LEVELS
                if base <= lvl <= max(top, base)
                and self.spell_slots_by_level.get(lvl, 0) > 0]

    def auto_pick_spells(self, class_name, level):
        """Pick a sensible random spell loadout (used by Quick Start / defaults)."""
        cantrip_budget, leveled_budget = self.spell_budget(class_name, level)
        top = self.max_spell_level(CLASSES.get(class_name, {}).get('caster'), level)
        picked = []
        # always start from the class's signature spells so a Cleric heals, etc.
        for key in CLASSES.get(class_name, {}).get('spells', []):
            entry = self.spell_catalog.get(key)
            if entry and entry[2] <= top and key in CLASS_SPELLS.get(class_name, []):
                picked.append(key)
        cantrips = [k for k in self.class_spell_list(class_name) if self.spell_catalog[k][2] == 0]
        leveled = [k for k in self.class_spell_list(class_name, max_level=top) if self.spell_catalog[k][2] > 0]
        random.shuffle(cantrips)
        random.shuffle(leveled)
        have_cantrips = sum(1 for k in picked if self.spell_catalog[k][2] == 0)
        have_leveled = len(picked) - have_cantrips
        for k in cantrips:
            if have_cantrips >= cantrip_budget:
                break
            if k not in picked:
                picked.append(k)
                have_cantrips += 1
        for k in leveled:
            if have_leveled >= leveled_budget:
                break
            if k not in picked:
                picked.append(k)
                have_leveled += 1
        return picked

    def roll_ability_score(self):
        """Roll 4d6 and drop the lowest die - the standard way to roll a stat."""
        rolls = sorted([random.randint(1, 6) for _ in range(4)])
        return sum(rolls[1:])

    def roll_stat_array(self):
        """Six 4d6-drop-lowest scores, highest first."""
        return sorted((self.roll_ability_score() for _ in range(6)), reverse=True)

    def randomize_abilities(self):
        """Roll every ability independently. Used before a class is chosen."""
        self.strength = self.roll_ability_score()
        self.dexterity = self.roll_ability_score()
        self.constitution = self.roll_ability_score()
        self.intelligence = self.roll_ability_score()
        self.wisdom = self.roll_ability_score()
        self.charisma = self.roll_ability_score()
        self.endurance = self.roll_ability_score()

    def update_derived_stats(self):
        """Recompute AC, attack bonus, damage and max HP from abilities and gear.

        Call this after ANY change to abilities, equipment, or level. Nothing here is
        stored as independent truth, so this can be called as often as you like and
        stats can never drift out of sync with their cause.

        Magic items feed in through gear_effects() (items.py), which is why a ring
        of protection shows up in your AC without any special case here.
        
"""
        gear = self.gear_effects()

        # --- Armour Class: armour + shield + gear + spells + stances ---
        armor_ac = ARMOR.get(getattr(self, 'equipped_armor', None), (0, 0))[0]
        shield_ac = SHIELDS.get(getattr(self, 'equipped_shield', None), (0, 0))[0]
        # Mage Armor: base AC 13 while you wear no actual armor (lasts until
        # a long rest - it is what lets a wizard walk the deep floors at all)
        base_ac = 13 if (getattr(self, 'mage_armor_active', False)
                         and not getattr(self, 'equipped_armor', None)) else 10
        self.player_ac = (base_ac + self.ability_mod('dexterity') + armor_ac + shield_ac
                          + gear.get('ac', 0)
                          + getattr(self, 'shield_bonus', 0)
                          + getattr(self, 'faith_bonus', 0)
                          + (2 if getattr(self, 'haste_active', False) else 0)
                          + (2 if getattr(self, 'defend_active', False) else 0))

        # --- weapon: damage die, attack bonus, damage bonus ---
        weapon = getattr(self, 'equipped_weapon', None) or 'unarmed strikes'
        die, atk_mod, _price = WEAPONS.get(weapon, (6, 0, 0))
        # finesse weapons let nimble characters use DEX instead of STR
        stat_mod = max(self.ability_mod('strength'), self.ability_mod('dexterity')) \
            if weapon in FINESSE else self.ability_mod('strength')
        self.player_damage_dice = die
        # proficiency (not a flat +2) is what keeps your attacks landing as
        # enemy AC climbs with the floors - levelling has to buy accuracy
        self.player_attack_bonus = (self.proficiency_bonus() + stat_mod + atk_mod
                                    + gear.get('atk', 0)
                                    + getattr(self, 'bless_bonus', 0))
        self.player_damage_bonus = (max(0, stat_mod) + gear.get('dmg', 0)
                                    + getattr(self, 'whetstone_bonus', 0))

        # --- damage reduction, from armour and trinkets and Barkskin ---
        self.damage_reduction = gear.get('dr', 0) + getattr(self, 'barkskin_dr', 0)

        # --- max health is fully derived (base + class die + CON + level + gear)
        #     so refreshes can never erase level-up gains.
        #     The pool is deliberately D&D-sized: potions (2d4+2), Hit Dice,
        #     trap dice and enemy damage dice are all written for this scale,
        #     so a bigger pool quietly turns every one of them into noise. ---
        con_mod = self.ability_mod('constitution')
        die_hp = getattr(self, 'class_hit_die', 8)
        per_level = die_hp // 2 + 2 + max(0, con_mod)
        self.max_health = max(1, PLAYER_HP_BASE + die_hp + con_mod
                              + (getattr(self, 'player_level', 1) - 1) * per_level
                              + gear.get('max_hp', 0)
                              + getattr(self, 'aid_bonus', 0))
        # gear that raises max HP must not leave you standing above it
        if getattr(self, 'health', 0) > self.max_health:
            self.health = self.max_health

    def proficiency_bonus(self):
        """+2 at level 1, and +1 more every four levels - the D&D curve.

        Feeds both weapon attacks (update_derived_stats above) and spell
        attacks (spells.py), so casters and martials stay accurate together.
        
"""
        return 2 + (max(1, getattr(self, 'player_level', 1)) - 1) // 4

    def clear_combat_effects(self):
        """Wipe every buff and condition that only lasts for one fight.

        Anything described as "for this fight" belongs here, so a new fight always
        starts from a known state rather than inheriting the last one. Called when a
        fight starts, when one ends, on death, and on load.

        DELIBERATELY NOT RESET HERE: self.poisoned and self.aid_bonus. Those are
        meant to follow you between fights until something cures them or you take a
        long rest, so wiping them at every encounter would quietly make poison
        harmless and Aid permanent.
        
"""
        self.temp_hp = 0
        self.bless_bonus = 0
        self.faith_bonus = 0
        self.barkskin_dr = 0
        self.whetstone_bonus = 0
        self.poison_weapon = 0
        self.radiant_weapon = 0
        self.check_bonus_temp = 0
        self.spirit_weapon = 0
        self.lingering = []
        self.burning_enemies = {}
        self.beacon_of_hope = False
        self.wall_of_force = False
        self.frost_armor = False
        self.greater_invis = False
        self.bane_active = False
        self.extra_shots = 0
        self.entangled = 0
        self.cursed_rounds = 0
        self.smoke_cover = False
        self.rage_active = False
        self.hunters_mark = False
        self.hex_active = False
        self.hex_spell_active = False
        self.smite_charge = 0
        self.true_strike_bonus = 0
        self.defend_active = False
        self.enemy_attack_penalty = 0
        # positioning is per-fight: the obstacle belongs to the room you fought
        # in, and cover/movement reset with it (do_attack rebuilds them)
        self.player_in_cover = False
        self.obstacle = None
        self.player_move_available = True
        self._pack_tactics_on = False
        self._narr_dmg_round = 0
        for attr in ('shield_bonus',):
            if hasattr(self, attr):
                try:
                    delattr(self, attr)
                except Exception:
                    pass

    def add_xp(self, amount):
        """Award XP and level up as many times as the total allows."""
        self.xp += amount
        self.log_message(f"You gain {amount} XP.")
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level_up()

    def level_up(self):
        """Advance one level: more HP, better slots, and new spells to choose.

        Every caster type gets its slots recomputed and is offered new spells if its
        budget grew. Fighters refresh their per-fight resources, Rogues their sneak
        attack.
        
"""
        self.player_level += 1
        # a new level is a new Hit Die, both in hand and in the maximum a Long
        # Rest restores you to - raising one without the other made the counter
        # read things like "3/1" and capped long rests at your level-1 total
        self.hit_dice_max = self.player_level
        self.hit_dice = min(self.hit_dice_max,
                            getattr(self, 'hit_dice', self.player_level - 1) + 1)
        # XP_GROWTH (data.py): 1.25 against linear kill rewards keeps levels
        # coming at depth; the old 1.4 dried progression up around level 6
        self.xp_to_next = int(self.xp_to_next * XP_GROWTH)
        # recompute max health for the new level and heal by the amount gained
        old_max = self.max_health
        self.update_derived_stats()
        gained = max(0, self.max_health - old_max)
        self.health = min(self.max_health, self.health + gained)
        # grant class improvements
        caster = getattr(self, 'caster_type', None)
        if caster:
            old_top = self.max_spell_level(caster, self.player_level - 1)
            new_max = self.compute_slots(caster, self.player_level)
            for lvl in SPELL_LEVELS:
                new_max.setdefault(lvl, 0)
            self.spell_slots_max_by_level = dict(new_max)
            # keep current slots as-is (a Long Rest restores them to the new max)
            top = self.max_spell_level(caster, self.player_level)
            if top > old_top:
                self.log_message(f"You can now cast level {top} spells!", color='important')
            # how many spells you should know now vs. how many you actually know
            cantrip_budget, leveled_budget = self.spell_budget(self.char_class, self.player_level)
            known_cantrips = sum(1 for k in self.known_spells
                                 if k in self.spell_catalog and self.spell_catalog[k][2] == 0)
            known_leveled = sum(1 for k in self.known_spells
                                if k in self.spell_catalog and self.spell_catalog[k][2] > 0)
            new_cantrips = max(0, cantrip_budget - known_cantrips)
            new_leveled = max(0, leveled_budget - known_leveled)
            if new_cantrips or new_leveled:
                self.root.after(120, lambda: self.open_spell_learning(new_cantrips, new_leveled, top))
        if self.char_class == 'Fighter':
            # regain action surge/second wind on level up
            self.action_surge_available = True
            self.second_wind_available = True
        elif self.char_class == 'Rogue':
            self.sneak_available = True

        self.play_sound('levelup')
        self.log_message(f"You advanced to level {self.player_level}! (+{gained} HP)", color="important")
        self.narrate(f"Level {self.player_level}!")
        if self.player_level in (5, 11):
            self.log_message("Your weapon work sharpens: every attack now rolls an extra damage die.",
                             color='important')

        # Ability Score Improvement levels. Queued rather than opened directly so
        # that it never fights the spell-learning dialog for the same moment.
        if self.player_level in ASI_LEVELS:
            self.asi_pending = getattr(self, 'asi_pending', 0) + 1
            self.log_message("Your training pays off: an Ability Score Improvement is waiting.",
                             color='important')
            try:
                self.root.after(400, self.open_asi_dialog)
            except Exception:
                pass

    def open_asi_dialog(self):
        """Spend a pending Ability Score Improvement: +2 to one ability, or +1 to two.

        Raises the BASE score, so it stacks with anything a magic item is adding on
        top. Scores stop at ABILITY_CAP. If several are owed they are spent one at a
        time, and the dialog simply reopens.
        
"""
        if getattr(self, 'asi_pending', 0) <= 0:
            return
        abilities = [('strength', 'STR'), ('dexterity', 'DEX'), ('constitution', 'CON'),
                     ('intelligence', 'INT'), ('wisdom', 'WIS'), ('charisma', 'CHA'),
                     ('endurance', 'END')]

        win = self.make_popup("Ability Score Improvement")
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text=f"Level {self.player_level}: Ability Score Improvement",
                  font=("Segoe UI", 13, "bold")).pack(anchor=tk.W)
        ttk.Label(frm, text=f"Raise one ability by 2, or two abilities by 1 each. "
                            f"Nothing may go above {ABILITY_CAP}.",
                  style='Dim.TLabel', wraplength=380, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 8))

        spent = {}   # ability -> points put in
        rows = {}

        def remaining():
            return 2 - sum(spent.values())

        def redraw():
            left = remaining()
            for key, (minus, plus, label) in rows.items():
                total = getattr(self, key, 10) + spent.get(key, 0)
                gear = self.gear_effects().get('stat', {}).get(key, 0)
                text = f"{total}" + (f"  (+{gear} from gear)" if gear else "")
                if spent.get(key):
                    text += f"   +{spent[key]}"
                label.configure(text=text)
                # +1 twice into one ability is the same as +2 into it, so the only
                # real limits are the points left and the hard cap
                can_add = left > 0 and total < ABILITY_CAP
                plus.state(['!disabled'] if can_add else ['disabled'])
                minus.state(['!disabled'] if spent.get(key) else ['disabled'])
            confirm_btn.state(['!disabled'] if left == 0 else ['disabled'])
            counter.configure(text=f"Points left: {left}")

        def add(key):
            if remaining() > 0 and getattr(self, key, 10) + spent.get(key, 0) < ABILITY_CAP:
                spent[key] = spent.get(key, 0) + 1
                redraw()

        def sub(key):
            if spent.get(key):
                spent[key] -= 1
                if not spent[key]:
                    del spent[key]
                redraw()

        for key, short in abilities:
            row = ttk.Frame(frm)
            row.pack(fill=tk.X, pady=(2, 2))
            ttk.Label(row, text=short, width=5).pack(side=tk.LEFT)
            lbl = ttk.Label(row, text="", width=22)
            lbl.pack(side=tk.LEFT)
            minus = ttk.Button(row, text="-", width=3, command=lambda k=key: sub(k))
            minus.pack(side=tk.RIGHT, padx=(4, 0))
            plus = ttk.Button(row, text="+", width=3, command=lambda k=key: add(k))
            plus.pack(side=tk.RIGHT)
            rows[key] = (minus, plus, lbl)

        counter = ttk.Label(frm, text="", style='Gold.TLabel')
        counter.pack(anchor=tk.W, pady=(8, 4))

        def confirm():
            for key, points in spent.items():
                setattr(self, key, min(ABILITY_CAP, getattr(self, key, 10) + points))
            gained = ', '.join(f"{k[:3].upper()} +{v}" for k, v in spent.items())
            self.asi_pending = max(0, getattr(self, 'asi_pending', 1) - 1)
            self.play_sound('levelup')
            self.log_message(f"Ability Score Improvement: {gained}.", color='important')
            win.destroy()
            self.update_derived_stats()
            self.refresh_stats()
            self.refresh_buttons()
            if getattr(self, 'asi_pending', 0) > 0:
                self.root.after(250, self.open_asi_dialog)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        confirm_btn = ttk.Button(btn_row, text="Confirm", command=confirm)
        confirm_btn.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Decide Later",
                   command=win.destroy).pack(side=tk.LEFT, padx=(8, 0))
        redraw()
        self.place_window(win, min_w=460, min_h=340)

    def open_spell_learning(self, cantrip_slots, spell_slots_to_learn, top_level):
        """Pick new spells on level up, limited to this class and spell level."""
        options = [k for k in self.class_spell_list(max_level=top_level)
                   if k not in self.known_spells]
        cantrip_options = [k for k in options if self.spell_catalog[k][2] == 0]
        leveled_options = [k for k in options if self.spell_catalog[k][2] > 0]
        if not (cantrip_slots and cantrip_options) and not (spell_slots_to_learn and leveled_options):
            return

        win = self.make_popup("Learn New Spells")
        outer = ttk.Frame(win, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        want_c = min(cantrip_slots, len(cantrip_options))
        want_l = min(spell_slots_to_learn, len(leveled_options))
        ttk.Label(outer, text=f"Level {self.player_level} {self.char_class}: "
                              f"choose {want_c} cantrip(s) and {want_l} spell(s).",
                  font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        frm = self.make_scrollable(outer, height=320)

        cantrip_vars, leveled_vars = {}, {}
        for lvl in range(0, top_level + 1):
            keys = [k for k in options if self.spell_catalog[k][2] == lvl]
            if not keys or (lvl == 0 and not want_c) or (lvl > 0 and not want_l):
                continue
            box = ttk.LabelFrame(frm, text="Cantrips" if lvl == 0 else f"Level {lvl}", padding=6)
            box.pack(fill=tk.X, pady=(4, 4))
            for key in keys:
                name, desc, _l, action = self.spell_catalog[key]
                var = tk.BooleanVar(value=False)
                cb = ttk.Checkbutton(box, text=f"{name} \u2014 {desc} [{action}]", variable=var)
                cb.pack(anchor=tk.W)
                (cantrip_vars if lvl == 0 else leveled_vars)[key] = (var, cb)

        info = ttk.Label(outer, text="")
        info.pack(anchor=tk.W, pady=(6, 0))

        def update_count(*_):
            c = sum(1 for v, _cb in cantrip_vars.values() if v.get())
            l = sum(1 for v, _cb in leveled_vars.values() if v.get())
            info.configure(text=f"Cantrips {c}/{want_c}   Spells {l}/{want_l}")
            for group, used, budget in ((cantrip_vars, c, want_c), (leveled_vars, l, want_l)):
                for var, cb in group.values():
                    try:
                        cb.state(['disabled'] if (used >= budget and not var.get()) else ['!disabled'])
                    except Exception:
                        pass

        for group in (cantrip_vars, leveled_vars):
            for var, _cb in group.values():
                var.trace_add('write', update_count)
        update_count()

        def confirm():
            picks = ([k for k, (v, _c) in cantrip_vars.items() if v.get()]
                     + [k for k, (v, _c) in leveled_vars.items() if v.get()])
            for key in picks:
                if key not in self.known_spells:
                    self.known_spells.append(key)
            if picks:
                names = ', '.join(self.spell_catalog[k][0] for k in picks)
                self.log_message(f"You learned: {names}.", color='important')
            win.destroy()
            self.refresh_stats()
            try:
                self.save_quick(self.quick_save_path)
            except Exception:
                pass

        def pick_for_me():
            random.shuffle(cantrip_options)
            random.shuffle(leveled_options)
            for key in cantrip_options[:want_c]:
                if key in cantrip_vars:
                    cantrip_vars[key][0].set(True)
            for key in leveled_options[:want_l]:
                if key in leveled_vars:
                    leveled_vars[key][0].set(True)

        row = ttk.Frame(outer)
        row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(row, text="Pick For Me", command=pick_for_me).pack(side=tk.LEFT)
        ttk.Button(row, text="Confirm", command=confirm).pack(side=tk.LEFT, padx=(8, 0))
        self.place_window(win, min_w=520, min_h=420)

    def handle_death(self):
        """You died: stop combat, clear buffs, and show the death screen."""
        self.close_dungeon_window()
        self.hide_combat_panel()
        self.play_sound('death')
        self.log_message("You died.", color="warning")
        self.narrate("You died.")
        self.in_combat = False
        self.current_event = None
        self.enemy_attack_pending = False
        # a death is the loudest thing the adaptive dial can hear
        try:
            self.record_fight_result(died=True)
        except Exception:
            pass
        self.end_haste(silent=True)
        self.clear_combat_effects()
        self.flash_death_screen()
