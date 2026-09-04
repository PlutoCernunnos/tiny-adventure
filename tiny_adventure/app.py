"""The game object itself.

TinyAdventureGUI is assembled from one mixin per area of the game. It is still
a single class at runtime - the mixins only decide which file each method is
written in. That means `self` is the whole game everywhere: code in combat.py
can call self.log_message() from ui.py with no imports and no plumbing.

    ui.py            the window and everything that redraws it
    character.py     creation, classes, levelling
    combat.py        turns, attacks, the action economy
    dungeon.py       floors, rooms, encounters
    items.py         inventory, equipment, shop
    spells.py        casting and the spellbook
    abilities.py     class abilities and resting
    persistence.py   saving, loading, settings
    menus.py         main menu and settings dialog
    companions.py    the hired ally: hiring, their turn, taking hits
    narrator.py      the spoken voice for key moments (TTS, no dependencies)
    audio_player.py  music and sound playback

    data.py          all the numbers, items, spells and bosses -
                     EDIT THIS ONE FOR BALANCE AND CONTENT
    audio.py         sound synthesis (standalone, no game dependency)
    paths.py         where saves/ and sounds/ live

ONE RULE: do not define the same method name in two mixins. Whichever comes
first in the class line below silently wins. If an edit seems to have no
effect, that is the first thing to check.

__init__ below sets up every attribute the game uses, then builds the window.
A new piece of state should be initialised there so it always exists.
"""
import os
import tkinter as tk

from .data import (SPELL_CATALOG, SPELL_LEVELS, COMMON_LOOT, ITEM_PRICES,
                   STARTING_KIT)
from .ui import UIMixin
from .character import CharacterMixin
from .combat import CombatMixin
from .dungeon import DungeonMixin
from .items import ItemsMixin
from .spells import SpellsMixin
from .abilities import ClassAbilityMixin
from .persistence import PersistenceMixin
from .menus import MenuMixin
from .companions import CompanionMixin
from .narrator import NarratorMixin
from .audio_player import AudioMixin
from .paths import game_dir


class TinyAdventureGUI(UIMixin, CharacterMixin, CombatMixin, DungeonMixin,
                       ItemsMixin, SpellsMixin, ClassAbilityMixin,
                       PersistenceMixin, MenuMixin, CompanionMixin,
                       NarratorMixin, AudioMixin):
    """The whole game. Behaviour lives in the mixins listed above."""

    def __init__(self, root):
        """Set up all game state, build the window, and open the main menu.

        Attribute defaults are established here first, then build_ui creates the
        widgets, then reset_game puts the character back to a blank slate. On a very
        first run the character creator opens instead of the main menu.
        
"""
        self.root = root
        self.root.title("Tiny Adventure")
        self.root.geometry("760x700")
        self.root.minsize(720, 620)
        self.root.resizable(True, True)

        self.health = 100
        self.gold = 10
        self.inventory = []
        # the random drop pool and the merchant's permanent stock both live in
        # data.py now, so adding an item there puts it into circulation
        self.items = list(COMMON_LOOT)
        self.shop_items = {name: ITEM_PRICES[name] for name in (
            'potion', 'greater potion', 'healing herbs', 'bandages', 'ration',
            'antidote', 'torch', 'lantern', 'rope', 'map', 'oil flask',
            'whetstone', 'net', 'smoke bomb', 'thieves tools', 'crowbar',
            'climbing gear', 'grappling hook', 'elixir of fortitude',
        )}
        self.name = "Adventurer"
        self.char_class = None
        self.subclass = None
        # class-related flags
        self.sneak_available = False
        self.sneak_active = False
        # spell slots organized by level: {1: count, ... 5: count}
        self.spell_slots_by_level = {lvl: 0 for lvl in SPELL_LEVELS}
        # per-round action economy
        self.player_action_available = True
        self.player_bonus_available = True
        # known spells and catalog
        self.known_spells = []
        self.spell_catalog = dict(SPELL_CATALOG)
        # track max slots separately so rests can restore to max
        self.spell_slots_max_by_level = {lvl: 0 for lvl in SPELL_LEVELS}
        self.second_wind_available = False
        self.action_surge_available = False
        self.enemy_attack_penalty = 0
        self.strength = 14
        self.dexterity = 13
        self.constitution = 12
        self.intelligence = 10
        self.wisdom = 11
        self.charisma = 9
        self.endurance = 12
        self.in_combat = False
        self.enemies = []
        self.target_index = 0
        self.combat_round = 0
        self.player_ac = 13
        self.player_attack_bonus = 2
        self.player_damage_dice = 6
        self.player_damage_bonus = 1
        self.shop_available = False
        self.current_event = None
        self.pending_enemies = []
        self.torch_active = False
        self.lantern_active = False
        self.buttons = {}
        self.character_created = False
        self.player_level = 1
        self.xp = 0
        self.xp_to_next = 100
        # equipment slots: weapon, armour, shield and one trinket
        self.equipped_weapon = None
        self.equipped_armor = None
        self.equipped_shield = None
        self.equipped_trinket = None
        # hit dice, the healing budget spent on short rests
        self.hit_dice = 1
        self.hit_dice_max = 1
        self.class_hit_die = 8
        # conditions and one-shot effects that outlive a single fight
        self.temp_hp = 0
        self.poisoned = 0
        self.aid_bonus = 0
        self.mage_armor_active = False   # Mage Armor holds until a long rest
        self.asi_pending = 0
        self.death_ward = False
        self.escape_ready = False
        self.guidance_ready = False
        self.lucky_bonus = 0
        self.damage_reduction = 0
        self.lingering = []
        self.burning_enemies = {}
        # tactics: positioning, cover, and the one-per-round free move
        self.player_move_available = True
        self.player_in_cover = False
        self.obstacle = None          # (name, description) or None, per fight
        # the hired companion: a dict of kind/name/hp, or None (companions.py)
        self.companion = None
        # adaptive difficulty: the quiet dial and the fights it remembers
        self.adaptive_enabled = True
        self.adaptive_mult = 1.0
        self.recent_fights = []
        # the narrator: spoken headlines for key moments (narrator.py).
        # '?' means "backend not probed yet"; everything else starts lazily.
        self.narrator_enabled = True
        self._narr_backend = '?'
        self._narr_queue = None
        self._narr_thread = None
        self._narr_proc = None
        self._narr_dmg_round = 0
        self._pack_start_count = 0
        self._pack_tactics_on = False
        self._fight_hp_start = 0
        self._fight_round_count = 0
        self._last_pos = (0, 0)
        self._fled_room_type = None
        self._shop_gear = []
        # log pacing: queued log lines are revealed this many ms apart so
        # combat is readable (0 = the old instant behaviour). getattr so tests
        # can override it on the class before __init__ runs; settings.json can
        # override it again via load_settings inside reset_game below.
        self.log_delay_ms = getattr(self, 'log_delay_ms', 200)
        self._log_queue = []
        self._log_pump_running = False

        self.build_ui()
        self.default_root_bg = self.root.cget("bg")
        self.default_log_bg = None
        self.default_list_bg = None
        self.reset_game()
        # autosave state
        self.autosave_enabled = True
        self.autosave_interval_ms = 30 * 1000  # 30 seconds
        self._autosave_job = None
        # sound effects (generates the wav files on first run)
        self.init_sounds()
        # On first launch, open the character creator to guide new players.
        try:
            root_dir = game_dir()
            flag = os.path.join(root_dir, '.tiny_adventure_first_run')
            self._creator_opened_on_start = False
            if not os.path.exists(flag):
                # prefill name if typed
                typed_name = self.name_entry.get().strip()
                self.open_character_creator(prefill_name=typed_name)
                self._creator_opened_on_start = True
        except Exception:
            pass
        # Open main menu unless we already opened the creator for first-run
        try:
            if not getattr(self, '_creator_opened_on_start', False):
                self.open_main_menu()
        except Exception:
            pass

def main():
    """Start the game: create the window, build the app, and hand over to Tk."""
    root = tk.Tk()
    app = TinyAdventureGUI(root)  # keep a reference so the app isn't garbage-collected
    root.mainloop()
