"""Class abilities and resting.

The Class Ability button routes through use_class_ability() to whichever menu
suits your class. Rogues and Fighters have their own; everyone else shares
open_generic_class_menu(), which shows only the abilities their class has.

Most abilities are once per rest, enforced by the once_per_rest wrapper inside
the generic menu. Anything that costs a bonus action should call
self.spend_bonus(), which returns False if it is already spent.

RESTING
    short rest  spend a Hit Die to heal; some resources come back
    long rest   full HP, all Hit Dice, all spell slots, everything refreshed
                (only at a camp room, marked C on the map)

Your Hit Dice are your real healing budget between camps: one die per short
rest, and you only get them back on a long one. How many you have left is
shown in the character panel, on the Stats screen, and in the rest dialog
itself, so there is never a reason to guess.

TO ADD AN ABILITY: write a nested function in open_generic_class_menu and add
a button for it under the right class.
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (WEAPONS, FINESSE, ARMOR, SHIELDS, MAGIC_ITEMS, CLASSES,
                   DIFFICULTIES, CLASS_SPELLS, SPELL_LEVELS,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, SPELL_CATALOG)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class ClassAbilityMixin:

    def use_class_ability(self):
        """Open the right ability menu for this character's class.

        Out of combat, casters get their spellbook instead - martial abilities need
        a fight to be useful.
        
"""
        if not self.in_combat:
            # spellcasters can still study their book; martial tricks need a fight
            if self.class_spell_list():
                self.open_spellbook()
            else:
                self.log_message("Class abilities are used in combat.")
            return

        cls = getattr(self, 'char_class', None)
        if cls == "Rogue":
            self.open_rogue_menu()
        elif cls == "Fighter":
            self.open_fighter_menu()
        elif cls in ("Wizard", "Sorcerer", "Bard", "Cleric", "Druid", "Warlock", "Paladin", "Ranger"):
            if cls in ("Wizard", "Sorcerer", "Bard", "Cleric", "Druid", "Warlock"):
                self.open_wizard_menu()  # the spellbook works for every caster
            if cls != "Wizard":
                self.open_generic_class_menu(cls)
        else:
            self.open_generic_class_menu(cls)

        self.refresh_stats()
        self.refresh_inventory()
        self.refresh_buttons()

    def open_generic_class_menu(self, cls):
        """The ability menu for every class without a bespoke one.

        Buttons appear only for abilities the class actually has. once_per_rest wraps
        anything that should not be spammable.
        
"""
        menu = self.make_popup(f"{cls} Abilities")
        frame = ttk.Frame(menu, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        def done():
            menu.destroy()
            self.refresh_stats()
            self.refresh_buttons()
            self.draw_combat()

        def once_per_rest(fn):
            def wrapped():
                if not getattr(self, 'class_resource_available', True):
                    self.log_message("You've spent that ability. Rest to recover it.")
                    return
                fn()
            return wrapped

        def rage():
            if not self.spend_bonus(): return
            self.class_resource_available = False
            self.rage_active = True
            self.play_sound('levelup')
            self.log_message("You fly into a RAGE: +2 damage for the rest of this fight!", color='important')
            done()

        def inspiration():
            if not self.spend_bonus(): return
            self.class_resource_available = False
            heal = min(self.max_health - self.health, random.randint(1, 6))
            self.health += heal
            self.true_strike_bonus = getattr(self, 'true_strike_bonus', 0) + 2
            self.play_sound('levelup')
            self.log_message(f"You sing a rousing verse: +2 on your next attack and {heal} HP restored.", color='important')
            done()

        def channel_divinity():
            if not self.player_action_available:
                self.log_message("Channel Divinity takes your action, which is already spent.")
                return
            self.player_action_available = False
            self.class_resource_available = False
            dmg = random.randint(1, 8) + random.randint(1, 8)
            self.play_sound('spell')
            self.log_message(f"Radiant light floods the room \u2014 {dmg} damage to every enemy!", color='important')
            for en in list(self.living_enemies()):
                self.hit_enemy(en, dmg, 'radiant')
            done()

        def wild_shape():
            if not self.spend_bonus(): return
            self.class_resource_available = False
            heal = min(self.max_health - self.health, 10)
            self.health += heal
            self.rage_active = True  # bestial fury: same +2 damage rider
            self.play_sound('levelup')
            self.log_message(f"You take on a bestial aspect: {heal} HP and +2 damage this fight!", color='important')
            done()

        def flurry():
            if not self.spend_bonus(): return
            target = self.current_target()
            if target is None:
                return
            roll = random.randint(1, 20)
            self.show_dice_roll(roll)
            total = roll + self.player_attack_bonus
            if roll == 20 or total >= target['ac']:
                dmg = random.randint(1, 6) * (2 if roll == 20 else 1)
                self.play_sound('hit')
                self.log_message(f"Flurry of Blows ({roll}+{self.player_attack_bonus}={total}) connects!", color='player')
                self.hit_enemy(target, dmg, 'unarmed')
            else:
                self.play_sound('miss')
                self.log_message(f"Flurry of Blows ({total}) misses.", color='warning')
            done()

        def stunning_strike():
            t = self.current_target()
            if t is None:
                return
            self.class_resource_available = False
            t['held'] = True
            self.play_sound('success')
            self.log_message(f"Stunning Strike! The {t['name']} reels and will miss its next turn.", color='important')
            done()

        def lay_on_hands():
            if not self.spend_bonus(): return
            self.class_resource_available = False
            heal = min(self.max_health - self.health, 15)
            self.health += heal
            self.play_sound('potion')
            self.log_message(f"Healing light flows from your hands: {heal} HP restored.", color='important')
            done()

        def divine_smite():
            if not self.spend_bonus(): return
            self.class_resource_available = False
            self.smite_charge = 2
            self.play_sound('spell')
            self.log_message("You call down divine wrath: your next hit deals +2d8 radiant damage!", color='important')
            done()

        def hunters_mark():
            if not self.spend_bonus(): return
            self.hunters_mark = True
            self.play_sound('success')
            self.log_message("Hunter's Mark: your weapon attacks deal +1d6 for this fight.", color='important')
            done()

        def hex():
            if not self.spend_bonus(): return
            self.hex_active = True
            self.play_sound('spell')
            self.log_message("A baleful curse settles on your foes: your hits deal +1d4 this fight.", color='important')
            done()

        def font_of_magic():
            if not self.spend_bonus(): return
            self.class_resource_available = False
            self.spell_slots_by_level[1] = self.spell_slots_by_level.get(1, 0) + 1
            self.play_sound('spell')
            self.log_message("Raw sorcery crackles through you: you recover a level 1 spell slot.", color='important')
            done()

        entries = {
            'Barbarian': [("Rage \u2014 +2 damage this fight [bonus, 1/rest]", once_per_rest(rage))],
            'Bard': [("Bardic Inspiration \u2014 +2 next attack, heal 1d6 [bonus, 1/rest]", once_per_rest(inspiration))],
            'Cleric': [("Channel Divinity \u2014 2d8 radiant to all enemies [action, 1/rest]", once_per_rest(channel_divinity))],
            'Druid': [("Wild Shape \u2014 heal 10, +2 damage this fight [bonus, 1/rest]", once_per_rest(wild_shape))],
            'Monk': [("Flurry of Blows \u2014 extra 1d6 strike [bonus]", flurry),
                     ("Stunning Strike \u2014 stun your target [1/rest]", once_per_rest(stunning_strike))],
            'Paladin': [("Lay on Hands \u2014 heal 15 [bonus, 1/rest]", once_per_rest(lay_on_hands)),
                        ("Divine Smite \u2014 next hit +2d8 [bonus, 1/rest]", once_per_rest(divine_smite))],
            'Ranger': [("Hunter's Mark \u2014 +1d6 on hits this fight [bonus]", hunters_mark)],
            'Sorcerer': [("Font of Magic \u2014 recover a L1 slot [bonus, 1/rest]", once_per_rest(font_of_magic))],
            'Warlock': [("Hex \u2014 +1d4 on hits this fight [bonus]", hex)],
        }
        for label, cb in entries.get(cls, []):
            ttk.Button(frame, text=label, command=cb).pack(fill=tk.X, pady=(4, 4))
        if not entries.get(cls):
            ttk.Label(frame, text="No special abilities \u2014 your spellbook is your power.").pack()
        ttk.Button(frame, text="Close", command=menu.destroy).pack(pady=(8, 0))
        self.place_window(menu, min_w=380, min_h=240)

    def open_rogue_menu(self):
        """Rogue abilities: preparing a sneak attack."""
        menu = self.make_popup("Rogue Abilities")
        frame = ttk.Frame(menu, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        def do_sneak():
            if not self.sneak_available:
                self.log_message("Sneak Attack not available.")
                return
            if not self.player_bonus_available:
                self.log_message("Preparing a Sneak Attack is a bonus action \u2014 yours is spent this round.")
                return
            self.player_bonus_available = False
            self.sneak_active = True
            self.sneak_available = False
            self.log_message("You prepare a Sneak Attack: next hit deals extra damage.")
            menu.destroy()

        ttk.Button(frame, text="Use Sneak Attack", command=do_sneak).pack(fill=tk.X, pady=(4, 4))
        ttk.Button(frame, text="Close", command=menu.destroy).pack(pady=(8, 0))
        self.place_window(menu, min_w=360, min_h=200)

    def open_fighter_menu(self):
        """Fighter abilities: Second Wind and Action Surge."""
        menu = self.make_popup("Fighter Maneuvers")
        frame = ttk.Frame(menu, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        def do_second_wind():
            if not self.second_wind_available:
                self.log_message("Second Wind not available.")
                return
            if not self.player_bonus_available:
                self.log_message("Second Wind is a bonus action \u2014 you've already used yours this round.")
                return
            self.player_bonus_available = False
            heal = min(self.max_health - self.health, 15)
            self.health += heal
            self.second_wind_available = False
            self.log_message(f"Second Wind: you regain {heal} HP.")
            menu.destroy()

        def do_action_surge():
            if not self.action_surge_available:
                self.log_message("Action Surge not available.")
                return
            # perform an extra Quick Attack immediately
            self.action_surge_available = False
            self.log_message("You surge into action and attack again!")
            self.perform_combat_attack("Action Surge Attack", attack_bonus_mod=2, damage_dice_count=1)
            menu.destroy()

        def do_trip():
            # Trip Attack: extra damage to your target; all foes attack at -2 this round
            self.enemy_attack_penalty = -2
            t = self.current_target() if self.in_combat else None
            if t:
                extra = random.randint(1, 6)
                self.log_message(f"Trip Attack! You knock the {t['name']} about for {extra} extra damage "
                                 "and throw the enemies off balance (-2 to their attacks this round).")
                self.hit_enemy(t, extra)
            menu.destroy()

        ttk.Button(frame, text="Second Wind", command=do_second_wind).pack(fill=tk.X, pady=(4, 4))
        ttk.Button(frame, text="Action Surge", command=do_action_surge).pack(fill=tk.X, pady=(4, 4))
        ttk.Button(frame, text="Trip Attack", command=do_trip).pack(fill=tk.X, pady=(4, 4))
        ttk.Button(frame, text="Close", command=menu.destroy).pack(pady=(8, 0))
        self.place_window(menu, min_w=380, min_h=240)

    def do_rest(self):
        # Short rest: small HP and partial slot restore. Long rest: full restore of HP and spell slots.
        """Rest to recover. Short rest spends a Hit Die; long rest restores everything.

        Long rests are only available at camp rooms, so healing stays a real decision.
        
"""
        if self.in_combat:
            self.log_message("You cannot rest during combat.")
            return

        win = self.make_popup("Rest")
        fr = ttk.Frame(win, padding=12)
        fr.pack(fill=tk.BOTH, expand=True)

        hd = getattr(self, 'hit_dice', 0)
        hd_max = getattr(self, 'hit_dice_max', getattr(self, 'player_level', 1))
        die = getattr(self, 'class_hit_die', 8)
        con = self.ability_mod('constitution')

        ttk.Label(fr, text="Rest", font=("Segoe UI", 13, "bold")).pack(anchor=tk.W)
        ttk.Label(fr, text=f"Health: {self.health} / {self.max_health}",
                  style='Gold.TLabel').pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(fr, text=f"Hit Dice remaining: {hd} of {hd_max}   (d{die} each, {con:+d} CON)",
                  style='Gold.TLabel', font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        if getattr(self, 'caster_type', None):
            slots = getattr(self, 'spell_slots_by_level', {})
            maxs = getattr(self, 'spell_slots_max_by_level', {})
            line = "   ".join(f"L{lvl}: {slots.get(lvl, 0)}/{maxs.get(lvl, 0)}"
                              for lvl in SPELL_LEVELS if maxs.get(lvl, 0))
            if line:
                ttk.Label(fr, text=f"Spell slots: {line}", style='Dim.TLabel').pack(anchor=tk.W)
        ttk.Label(fr, text=("A Short Rest spends one Hit Die and is risky - "
                            "something may find you. A Long Rest needs a camp (C) "
                            "and restores everything, Hit Dice included."),
                  style='Dim.TLabel', wraplength=380, justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 8))
        if hd <= 0:
            ttk.Label(fr, text="You are out of Hit Dice. Only a Long Rest will bring them back.",
                      style='Dim.TLabel', wraplength=380).pack(anchor=tk.W, pady=(0, 6))
        if not getattr(self, 'can_long_rest', False):
            ttk.Label(fr, text="No camp here, so a Long Rest is not available.",
                      style='Dim.TLabel', wraplength=380).pack(anchor=tk.W, pady=(0, 6))

        def short_rest():
            # spend one Hit Die to heal (die size depends on your class)
            if getattr(self, 'hit_dice', 0) <= 0:
                self.log_message("You have no Hit Dice left \u2014 take a Long Rest at a camp (C) to recover them.")
                return
            self.hit_dice -= 1
            die = getattr(self, 'class_hit_die', 8)
            self.temp_hp = 0  # temporary HP does not survive a rest
            roll = random.randint(1, die)
            self.show_dice_roll(roll, sides=die, label=f"d{die}")
            healed = self.heal_player(max(1, roll + self.ability_mod('constitution')),
                                      f"Short Rest: you spend a Hit Die (d{die}: {roll})")
            remaining = self.hit_dice
            self.log_message(f"{remaining} Hit Dice remain of "
                             f"{getattr(self, 'hit_dice_max', self.player_level)}.",
                             color='important' if remaining else 'warning')
            # short-rest class recovery
            cls = getattr(self, 'char_class', None)
            if cls == 'Fighter':
                self.action_surge_available = True
                self.second_wind_available = True
            if cls == 'Rogue':
                self.sneak_available = True
            if cls == 'Bard':
                self.class_resource_available = True
            if cls == 'Warlock':
                # pact magic: warlock slots come back on a short rest
                self.spell_slots_by_level = dict(self.spell_slots_max_by_level)
                self.log_message("Your pact magic replenishes.", color='important')
            win.destroy()
            self.refresh_stats()
            self.refresh_inventory()
            self.refresh_buttons()
            # THE DOWNSIDE: resting in a dungeon is noisy. Something may find you.
            if random.random() < 0.35:
                floor = self.dungeon.get('floor', 1) if getattr(self, 'dungeon', None) else 1
                self.pending_enemies = self.make_enemy_pack(floor)
                self.current_event = 'enemy'
                self.play_sound('enemy_hit')
                names = ', '.join(e['name'] for e in self.pending_enemies)
                self.log_message(f"Your rest is interrupted \u2014 {names} stumble upon your camp!", color='enemy')
                self.close_dungeon_window()
                self.do_attack()

        def long_rest():
            # long rest can only be used in a camp / safe spot
            if not getattr(self, 'can_long_rest', False):
                self.log_message("You can only Long Rest at a camp or safe location.")
                return
            # full heal and restore all spell slots to max
            self.aid_bonus = 0        # Aid's bonus HP expires with the night
            self.mage_armor_active = False   # and the film of force fades as you sleep
            self.poisoned = 0         # sleeping it off works
            self.temp_hp = 0
            self.clear_combat_effects()
            self.update_derived_stats()
            self.health = self.max_health
            self.hit_dice_max = self.player_level
            self.hit_dice = self.hit_dice_max
            self.class_resource_available = True
            self.death_ward = False
            self.escape_ready = False
            # restore current slots to max for all known levels
            for lvl, mx in self.spell_slots_max_by_level.items():
                self.spell_slots_by_level[lvl] = mx
            # restore class resources
            if getattr(self, 'char_class', None) == 'Fighter':
                self.action_surge_available = True
                self.second_wind_available = True
            if getattr(self, 'char_class', None) == 'Rogue':
                self.sneak_available = True
            # restore per-round availability
            self.player_action_available = True
            self.player_bonus_available = True
            # leaving the camp available after long rest (do not consume)

            self.log_message(f"Long Rest: full HP, all {self.hit_dice} Hit Dice, every spell slot, "
                             "and all class resources are back.", color='important')
            win.destroy()
            self.refresh_stats()
            self.refresh_inventory()
            self.refresh_buttons()
            try:
                self.save_quick(self.quick_save_path)
            except Exception:
                pass

        short_btn = ttk.Button(fr, text=f"Short Rest \u2014 spend a Hit Die (d{die} {con:+d})",
                               command=short_rest)
        short_btn.pack(fill=tk.X, pady=(6, 4))
        if hd <= 0:
            short_btn.state(['disabled'])
        long_btn = ttk.Button(fr, text="Long Rest \u2014 restore everything (camp only)",
                              command=long_rest)
        long_btn.pack(fill=tk.X, pady=(0, 6))
        if not getattr(self, 'can_long_rest', False):
            long_btn.state(['disabled'])
        ttk.Button(fr, text="Cancel", command=win.destroy).pack()
        self.place_window(win, min_w=460, min_h=260)
