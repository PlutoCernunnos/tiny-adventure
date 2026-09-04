"""Saving, loading, autosave, and settings.

Saves are plain JSON in the saves/ folder next to the game, so they can be
inspected and hand-edited if something goes wrong.

    game_state_dict()   character -> a dict ready for JSON
    apply_game_state()  that dict -> the character again

ADDING SOMETHING TO SAVES: add it to game_state_dict, then read it back in
apply_game_state with a getattr-style default. Old saves lack the new key, so
always supply a fallback rather than assuming it is there.

TWO THINGS DELIBERATELY NOT SAVED
    combat  - you never resume mid-fight, so a save cannot strand you in one
    buffs   - Haste, Bless, Barkskin and friends are cleared on load rather
              than restored. Conditions that are meant to outlast a fight
              (poison, a pending Ability Score Improvement, Aid's extra HP)
              ARE saved, since they are part of your character rather than
              part of a particular encounter.

A JSON QUIRK worth knowing: JSON turns integer dict keys into strings, which
silently broke spell slots in an earlier version. _slot_dict in
apply_game_state converts them back. Any future dict with integer keys needs
the same treatment.

Settings (volume, difficulty, autosave) live separately in settings.json and
persist across characters.
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


class PersistenceMixin:

    # --- Save/Load support ---
    def game_state_dict(self):
        # Collect serializable game state
        """Collect everything worth saving into a JSON-friendly dict.

        Add new saved fields here, and read them back in apply_game_state.
        
"""
        state = {
            'name': self.name,
            'char_class': self.char_class,
            'subclass': getattr(self, 'subclass', None),
            'character_created': self.character_created,
            'strength': self.strength,
            'dexterity': self.dexterity,
            'constitution': self.constitution,
            'intelligence': self.intelligence,
            'wisdom': self.wisdom,
            'charisma': self.charisma,
            'endurance': self.endurance,
            'health': self.health,
            'max_health': getattr(self, 'max_health', 0),
            'gold': self.gold,
            'inventory': list(self.inventory),
            'known_spells': list(getattr(self, 'known_spells', [])),
            'spell_slots_by_level': dict(getattr(self, 'spell_slots_by_level', {})),
            'spell_slots_max_by_level': dict(getattr(self, 'spell_slots_max_by_level', {})),
            'player_level': self.player_level,
            'xp': self.xp,
            'xp_to_next': self.xp_to_next,
            'map_state': getattr(self, 'map_state', None),
            'current_event': self.current_event,
            'can_long_rest': getattr(self, 'can_long_rest', False),
            'second_wind_available': getattr(self, 'second_wind_available', False),
            'equipped_weapon': getattr(self, 'equipped_weapon', None),
            'equipped_armor': getattr(self, 'equipped_armor', None),
            'equipped_shield': getattr(self, 'equipped_shield', None),
            'equipped_trinket': getattr(self, 'equipped_trinket', None),
            'asi_pending': getattr(self, 'asi_pending', 0),
            'poisoned': getattr(self, 'poisoned', 0),
            'aid_bonus': getattr(self, 'aid_bonus', 0),
            'mage_armor_active': getattr(self, 'mage_armor_active', False),
            'death_ward': getattr(self, 'death_ward', False),
            'hit_dice': getattr(self, 'hit_dice', 1),
            'hit_dice_max': getattr(self, 'hit_dice_max', getattr(self, 'player_level', 1)),
            'class_hit_die': getattr(self, 'class_hit_die', 8),
            'cast_stat': getattr(self, 'cast_stat', None),
            'caster_type': getattr(self, 'caster_type', None),
            'class_resource_available': getattr(self, 'class_resource_available', True),
            'action_surge_available': getattr(self, 'action_surge_available', False),
            'sneak_available': getattr(self, 'sneak_available', False),
            'companion': dict(self.companion) if getattr(self, 'companion', None) else None,
            'adaptive_mult': float(getattr(self, 'adaptive_mult', 1.0)),
            'dungeon': self.dungeon_to_dict(),
        }
        return state

    def dungeon_to_dict(self):
        """Convert the dungeon to JSON-friendly form (tuple keys -> 'x,y' strings)."""
        d = getattr(self, 'dungeon', None)
        if not d:
            return None
        return {
            'floor': d['floor'],
            'size': d['size'],
            'pos': list(d['pos']),
            'boss_floor': d.get('boss_floor', False),
            'boss_defeated': d.get('boss_defeated', False),
            'rooms': {f"{x},{y}": room for (x, y), room in d['rooms'].items()},
        }

    def dungeon_from_dict(self, data):
        """Rebuild the dungeon from JSON, turning 'x,y' strings back into (x, y)."""
        if not data:
            return None
        rooms = {}
        for key, room in data.get('rooms', {}).items():
            x, y = key.split(',')
            rooms[(int(x), int(y))] = room
        return {
            'floor': data.get('floor', 1),
            'size': data.get('size', 5),
            'pos': tuple(data.get('pos', [0, 0])),
            'boss_floor': data.get('boss_floor', False),
            'boss_defeated': data.get('boss_defeated', False),
            'rooms': rooms,
        }

    def apply_game_state(self, state):
        # Restore state from dict
        """Restore a character from a saved dict.

        Unknown or missing keys fall back to current values, so old saves keep
        loading after new fields are added.
        
"""
        self.name = state.get('name', self.name)
        self.char_class = state.get('char_class', self.char_class)
        # older saves have no subclass; None is a valid, effect-free value
        self.subclass = state.get('subclass', None)
        self.character_created = state.get('character_created', self.character_created)
        self.strength = state.get('strength', self.strength)
        self.dexterity = state.get('dexterity', self.dexterity)
        self.constitution = state.get('constitution', self.constitution)
        self.intelligence = state.get('intelligence', self.intelligence)
        self.wisdom = state.get('wisdom', self.wisdom)
        self.charisma = state.get('charisma', self.charisma)
        self.endurance = state.get('endurance', self.endurance)
        self.health = state.get('health', self.health)
        self.max_health = state.get('max_health', getattr(self, 'max_health', 0))
        self.gold = state.get('gold', self.gold)
        self.inventory = list(state.get('inventory', self.inventory))
        self.known_spells = list(state.get('known_spells', getattr(self, 'known_spells', [])))
        # JSON converts integer dict keys to strings, so normalize them back to
        # ints or slots silently break after loading a save (rests seem to fail)
        # JSON turns integer dict keys into strings, which silently broke spell
        # slots in an earlier version - rests appeared to do nothing. Any dict
        # with integer keys needs converting back like this on load.
        def _slot_dict(raw):
            out = {}
            for k, v in dict(raw or {}).items():
                try:
                    out[int(k)] = int(v)
                except (TypeError, ValueError):
                    pass
            return out
        self.spell_slots_by_level = _slot_dict(state.get('spell_slots_by_level', getattr(self, 'spell_slots_by_level', {})))
        self.spell_slots_max_by_level = _slot_dict(state.get('spell_slots_max_by_level', getattr(self, 'spell_slots_max_by_level', {})))
        self.player_level = state.get('player_level', self.player_level)
        self.xp = state.get('xp', self.xp)
        self.xp_to_next = state.get('xp_to_next', self.xp_to_next)
        self.map_state = state.get('map_state', getattr(self, 'map_state', None))
        self.current_event = state.get('current_event', self.current_event)
        self.can_long_rest = state.get('can_long_rest', getattr(self, 'can_long_rest', False))
        self.dungeon = self.dungeon_from_dict(state.get('dungeon'))
        self.close_dungeon_window()  # reopen via Explore to see the loaded floor
        # combat isn't saved, so never resume into a half-restored fight
        self.in_combat = False
        self.enemies = []
        self.pending_enemies = []
        self.enemy_attack_pending = False
        self.end_haste(silent=True)
        self.clear_combat_effects()
        self.player_action_available = True
        self.player_bonus_available = True
        self.hide_combat_panel()
        self._last_pos = self.dungeon['pos'] if getattr(self, 'dungeon', None) else (0, 0)
        self._fled_room_type = None
        if self.current_event == 'enemy':
            self.current_event = None
        # class resources (older saves simply keep their current values)
        self.second_wind_available = state.get('second_wind_available', getattr(self, 'second_wind_available', False))
        self.action_surge_available = state.get('action_surge_available', getattr(self, 'action_surge_available', False))
        self.sneak_available = state.get('sneak_available', getattr(self, 'sneak_available', False))
        self.equipped_weapon = state.get('equipped_weapon', getattr(self, 'equipped_weapon', None))
        self.equipped_armor = state.get('equipped_armor', getattr(self, 'equipped_armor', None))
        # slots added after the first release, so old saves simply have none
        self.equipped_shield = state.get('equipped_shield', None)
        self.equipped_trinket = state.get('equipped_trinket', None)
        self.asi_pending = state.get('asi_pending', 0)
        self.poisoned = state.get('poisoned', 0)
        self.aid_bonus = state.get('aid_bonus', 0)
        self.mage_armor_active = state.get('mage_armor_active', False)
        self.death_ward = state.get('death_ward', False)
        self.hit_dice = state.get('hit_dice', getattr(self, 'hit_dice', self.player_level))
        self.hit_dice_max = state.get('hit_dice_max', max(self.hit_dice, self.player_level))
        self.class_hit_die = state.get('class_hit_die', getattr(self, 'class_hit_die', 8))
        self.cast_stat = state.get('cast_stat', getattr(self, 'cast_stat', None))
        self.caster_type = state.get('caster_type', getattr(self, 'caster_type', None))
        self.class_resource_available = state.get('class_resource_available', True)
        # the companion and the adaptive dial travel with the character;
        # older saves simply have neither
        comp = state.get('companion')
        self.companion = dict(comp) if comp else None
        try:
            self.adaptive_mult = float(state.get('adaptive_mult', 1.0))
        except (TypeError, ValueError):
            self.adaptive_mult = 1.0
        self.recent_fights = []
        # recompute derived stats & refresh UI
        self.update_derived_stats()
        self.refresh_stats()
        self.refresh_inventory()
        self.refresh_buttons()
        if getattr(self, 'asi_pending', 0):
            self.log_message("You still have an Ability Score Improvement to spend.",
                             color='important')
            try:
                self.root.after(500, self.open_asi_dialog)
            except Exception:
                pass

    def save_game(self, path):
        """Write the game to a chosen file."""
        state = self.game_state_dict()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)

    def load_game(self, path):
        """Load a game from a file and refresh the whole UI."""
        with open(path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        self.apply_game_state(state)

    def save_quick(self, path):
        """Write a quick save, used for autosave too."""
        try:
            self.save_game(path)
        except Exception:
            # ensure folder exists
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.save_game(path)

    # Autosave scheduling
    def start_autosave(self):
        """Begin the periodic autosave timer."""
        if not self.autosave_enabled:
            return
        # cancel existing
        self.stop_autosave()
        # schedule
        self._autosave_job = self.root.after(self.autosave_interval_ms, self._do_autosave)

    def stop_autosave(self):
        """Cancel the autosave timer."""
        if self._autosave_job:
            try:
                self.root.after_cancel(self._autosave_job)
            except Exception:
                pass
            self._autosave_job = None

    def _do_autosave(self):
        """Autosave, then schedule the next one."""
        try:
            if getattr(self, 'character_created', False) and self.autosave_enabled:
                self.save_quick(self.autosave_path)
        except Exception:
            pass
        # reschedule only while autosave is enabled
        if self.autosave_enabled:
            self._autosave_job = self.root.after(self.autosave_interval_ms, self._do_autosave)
        else:
            self._autosave_job = None

    def save_settings(self):
        """Write settings (volume, difficulty, autosave) to settings.json."""
        data = {
            'autosave_enabled': bool(getattr(self, 'autosave_enabled', True)),
            'autosave_interval_ms': int(getattr(self, 'autosave_interval_ms', 30000)),
            'sound_enabled': bool(getattr(self, 'sound_enabled', True)),
            'music_enabled': bool(getattr(self, 'music_enabled', True)),
            'music_volume': int(getattr(self, 'music_volume', 60)),
            'sfx_volume': int(getattr(self, 'sfx_volume', 80)),
            'difficulty': getattr(self, 'difficulty', 'Normal'),
            'adaptive_enabled': bool(getattr(self, 'adaptive_enabled', True)),
            'narrator_enabled': bool(getattr(self, 'narrator_enabled', True)),
            'log_delay_ms': int(getattr(self, 'log_delay_ms', 200)),
            'save_folder': getattr(self, 'save_folder', ''),
        }
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def load_settings(self):
        """Read settings.json if it exists, falling back to defaults."""
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.autosave_enabled = bool(data.get('autosave_enabled', True))
                self.autosave_interval_ms = int(data.get('autosave_interval_ms', 30000))
                self.sound_enabled = bool(data.get('sound_enabled', True))
                self.music_enabled = bool(data.get('music_enabled', True))
                self.music_volume = max(0, min(100, int(data.get('music_volume', 60))))
                self.sfx_volume = max(0, min(100, int(data.get('sfx_volume', 80))))
                self.difficulty = data.get('difficulty', 'Normal')
                self.adaptive_enabled = bool(data.get('adaptive_enabled', True))
                self.narrator_enabled = bool(data.get('narrator_enabled', True))
                # older settings files lack this key; keep whatever is set now
                # (the default, or a test's override) rather than forcing 200
                self.log_delay_ms = max(0, min(2000, int(data.get(
                    'log_delay_ms', getattr(self, 'log_delay_ms', 200)))))
                folder = data.get('save_folder')
                if folder:
                    self.save_folder = folder
                    self.quick_save_path = os.path.join(self.save_folder, 'quicksave.json')
                    self.autosave_path = os.path.join(self.save_folder, 'autosave.json')
        except Exception:
            pass
