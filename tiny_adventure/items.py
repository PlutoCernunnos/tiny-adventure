"""Inventory, equipment, magic items, and the shop.

HOW THE BAG IS STORED
self.inventory is a flat list with one entry per item: two potions means
['potion', 'potion']. Stacking is purely a display trick - refresh_inventory
groups them into 'potion  x2' rows and remembers which row maps back to which
item in self._inventory_rows.

That matters when you write code: to add two potions, append twice. To check
how many you have, use self.inventory.count('potion'). Never assume a row in
the listbox is a single item.

THE FOUR EQUIPMENT SLOTS
    weapon    what you swing
    armor     what you wear
    shield    what you hold in the off hand
    trinket   one ring, cloak, amulet, belt or pair of boots

Each maps to an attribute via SLOT_ATTR in data.py (equipped_weapon and so
on). Press Gear to see all four at once and swap between them.

MAGIC ITEMS
Everything a magic item does is declared as data in MAGIC_ITEMS (data.py) and
totalled up by gear_effects() below. Nothing reads MAGIC_ITEMS directly except
that one method, so a new item with an existing effect key needs no code at
all - update_derived_stats and perform_combat_attack pick it up for free.

    gear_effects()   every equipped item's effects, added together

USING AN ITEM IN COMBAT
    a consumable ....... costs your BONUS action
    equipping gear ..... costs your full ACTION
Out of combat both are free.

WHERE TO CHANGE THINGS

    What an item does ........... apply_item_effect
    An item's description ....... ITEM_INFO in data.py
    What a magic item grants .... MAGIC_ITEMS in data.py
    What the shop sells ......... open_shop_window, self.shop_items
    Weapon and armour stats ..... WEAPONS / ARMOR / SHIELDS in data.py
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (WEAPONS, FINESSE, RANGED, ARMOR, SHIELDS, MAGIC_ITEMS,
                   EQUIP_SLOTS, SLOT_ATTR, EQUIPPABLE, MAGIC_BY_RARITY,
                   MUNDANE_WEAPONS, MUNDANE_ARMOR, MUNDANE_SHIELDS,
                   CLASSES, DIFFICULTIES, CLASS_SPELLS,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, ITEM_PRICES, SELL_RATE, VALUABLES, SCROLLS,
                   COMMON_LOOT, DEEP_LOOT, SPELL_CATALOG)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class ItemsMixin:

    # ------------------------------------------------------------------ gear

    def equipped_items(self):
        """The name in each equipment slot, as {slot: name or None}."""
        return {slot: getattr(self, SLOT_ATTR[slot], None) for slot in EQUIP_SLOTS}

    def gear_effects(self):
        """Everything your equipped magic items grant, added together.

        Returns a dict of effect keys - ac, atk, dmg, dr, stat, bonus_damage and so
        on, exactly as documented on MAGIC_ITEMS in data.py. Anything not granted by
        anything you are wearing is simply absent, so read it with .get().

        This is the single place magic item effects are collected. update_derived_stats
        and perform_combat_attack both call it, which is why adding an item with an
        existing effect key needs no code changes anywhere.
        
"""
        totals = {'stat': {}, 'slot_bonus': {}, 'bonus_damage': [], 'crit_range': 20}
        flat = ('ac', 'atk', 'dmg', 'spell_atk', 'max_hp', 'dr', 'regen',
                'check_bonus', 'flee_bonus')
        for key in flat:
            totals[key] = 0
        totals['light'] = False

        for slot in EQUIP_SLOTS:
            name = getattr(self, SLOT_ATTR[slot], None)
            info = MAGIC_ITEMS.get(name)
            if not info:
                continue
            for key in flat:
                totals[key] += info.get(key, 0)
            for stat, amount in info.get('stat', {}).items():
                totals['stat'][stat] = totals['stat'].get(stat, 0) + amount
            for lvl, amount in info.get('slot_bonus', {}).items():
                totals['slot_bonus'][lvl] = totals['slot_bonus'].get(lvl, 0) + amount
            if info.get('bonus_damage'):
                totals['bonus_damage'].append((info['bonus_damage'],
                                               info.get('damage_type', 'magic')))
            if info.get('crit_range'):
                totals['crit_range'] = min(totals['crit_range'], info['crit_range'])
            if info.get('light'):
                totals['light'] = True

        # your subclass grants effects through the very same keys, so folding
        # it in here means AC, attacks, crits, DR, regeneration, checks and
        # fleeing all pick it up with no code anywhere else
        sub = self.subclass_effects()
        if sub:
            for key in flat:
                totals[key] += sub.get(key, 0)
            for stat, amount in sub.get('stat', {}).items():
                totals['stat'][stat] = totals['stat'].get(stat, 0) + amount
            if sub.get('bonus_damage'):
                totals['bonus_damage'].append((sub['bonus_damage'],
                                               sub.get('damage_type', 'magic')))
            if sub.get('crit_range'):
                totals['crit_range'] = min(totals['crit_range'], sub['crit_range'])
        return totals

    def item_slot(self, item):
        """Which equipment slot an item goes in, or None if it is not gear."""
        return EQUIPPABLE.get(item)

    def item_price(self, item):
        """What a shop charges for one of these. 0 for anything with no listed price."""
        if item in MAGIC_ITEMS:
            return MAGIC_ITEMS[item].get('price', 0)
        if item in WEAPONS:
            return WEAPONS[item][2]
        if item in ARMOR:
            return ARMOR[item][1]
        if item in SHIELDS:
            return SHIELDS[item][1]
        return ITEM_PRICES.get(item, 0)

    def item_rarity(self, item):
        """The rarity label of a magic item, or None for ordinary gear."""
        return MAGIC_ITEMS.get(item, {}).get('rarity')

    # ------------------------------------------------------------- inventory

    def inventory_stacks(self):
        """Inventory as [(item, count), ...] in the order things were first picked up."""
        order = []
        counts = {}
        for item in self.inventory:
            if item not in counts:
                counts[item] = 0
                order.append(item)
            counts[item] += 1
        return [(item, counts[item]) for item in order]

    def refresh_inventory(self):
        """Redraw the bag, collapsing duplicates into 'potion  x3' rows.

        Builds self._inventory_rows, which maps each visible row back to the plain
        item name, and preserves whatever was selected.
        
"""
        previous = self.selected_item()
        self.inventory_list.delete(0, tk.END)
        # maps each visible row back to the plain item name
        self._inventory_rows = []
        equipped = set(v for v in self.equipped_items().values() if v)
        stacks = self.inventory_stacks()
        if stacks:
            for item, count in stacks:
                label = item if count == 1 else f"{item}  x{count}"
                if item in equipped:
                    label += "  (equipped)"
                elif item in MAGIC_ITEMS:
                    label += f"  [{MAGIC_ITEMS[item]['rarity']}]"
                self.inventory_list.insert(tk.END, label)
                self._inventory_rows.append(item)
        else:
            self.inventory_list.insert(tk.END, "(empty)")
        # keep the highlight on whatever the player had selected
        if previous in self._inventory_rows:
            idx = self._inventory_rows.index(previous)
            self.inventory_list.selection_set(idx)
        self.show_item_details()

    def selected_item(self):
        """The plain item name for the highlighted row, or None."""
        rows = getattr(self, '_inventory_rows', [])
        selection = self.inventory_list.curselection()
        if selection and selection[0] < len(rows):
            return rows[selection[0]]
        return None

    def describe_item(self, item):
        """A one-line explanation of what an item is and does.

        Weapon, shield and armour text is generated from the tables in data.py, so
        their stats can never fall out of step. Magic items append whatever
        MAGIC_ITEMS says they grant on top of that.
        
"""
        magic = MAGIC_ITEMS.get(item)
        parts = []
        if item in WEAPONS:
            die, atk_mod, price = WEAPONS[item]
            sign = '+' if atk_mod >= 0 else ''
            bits = [f"d{die} damage", f"{sign}{atk_mod} to hit", f"worth {price} gold"]
            if item in FINESSE:
                bits.append("finesse (STR or DEX)")
            if item in RANGED:
                bits.append("ranged")
            kind = f"{magic['rarity']} weapon" if magic else "Weapon"
            parts.append(f"{kind} - {', '.join(bits)}.")
        elif item in ARMOR:
            ac, price = ARMOR[item]
            kind = f"{magic['rarity']} armor" if magic else "Armor"
            parts.append(f"{kind} - +{ac} AC, worth {price} gold.")
        elif item in SHIELDS:
            ac, price = SHIELDS[item]
            kind = f"{magic['rarity']} shield" if magic else "Shield"
            parts.append(f"{kind} - +{ac} AC, worth {price} gold.")
        elif magic:
            parts.append(f"{magic['rarity']} {magic['slot']} - worth {magic.get('price', 0)} gold.")
        else:
            kind, text = ITEM_INFO.get(item, ('Item', 'No one is quite sure what this does.'))
            parts.append(f"{kind} - {text}")
            if item in VALUABLES:
                parts.append(f"Sells for about {int(self.item_price(item) * SELL_RATE)} gold.")
        if magic:
            parts.append(magic['desc'])
        if self.item_slot(item):
            parts.append("Use Item (or the Gear screen) to equip it.")
        return ' '.join(parts)

    def show_item_details(self):
        """Update the description line under the inventory list."""
        if not hasattr(self, 'item_detail_label'):
            return
        item = self.selected_item()
        if not item:
            self.item_detail_label.configure(text="Select an item to see what it does.")
            return
        count = self.inventory.count(item)
        header = item if count <= 1 else f"{item} (x{count})"
        self.item_detail_label.configure(text=f"{header}: {self.describe_item(item)}")

    def do_use_item(self):
        """Use the selected item, charging the right part of your turn.

        Consumables cost your bonus action in combat; swapping gear costs your
        action. Out of combat neither costs anything.
        
"""
        if not self.inventory:
            self.log_message("You have no items to use.")
            return

        item = self.selected_item() or self.inventory[0]

        # In a fight, rummaging through your pack costs your bonus action.
        # Swapping gear is a bigger job and takes your whole action instead.
        if self.in_combat:
            if getattr(self, 'enemy_attack_pending', False):
                self.log_message("The enemies are still taking their turn.")
                return
            equipping = bool(self.item_slot(item))
            if equipping:
                if not getattr(self, 'player_action_available', True):
                    self.log_message("Changing gear takes your action, and yours is spent this round.")
                    return
            elif not getattr(self, 'player_bonus_available', True):
                self.log_message("Using an item is a bonus action, and yours is spent this round.")
                return
            used = self.apply_item_effect(item)
            if used:
                if equipping:
                    self.spend_action()
                else:
                    self.player_bonus_available = False
                    self.log_message("(That used your bonus action.)")
                self.refresh_stats()
                self.refresh_buttons()
            return

        self.apply_item_effect(item)

    # ------------------------------------------------------------- equipping

    def equip_item(self, item):
        """Equip anything into its own slot, returning whatever was there to the bag."""
        slot = self.item_slot(item)
        if not slot:
            self.log_message(f"The {item} is not something you can wear or wield.")
            return False
        attr = SLOT_ATTR[slot]
        previous = getattr(self, attr, None)
        if previous == item:
            self.log_message(f"You are already using the {item}.")
            return False
        setattr(self, attr, item)
        # the new gear leaves your pack; the old gear goes back into it
        if item in self.inventory:
            self.inventory.remove(item)
        if previous and previous != 'unarmed strikes':
            self.inventory.append(previous)
        self.play_sound('equip')
        verb = {'weapon': 'wield', 'armor': 'don',
                'shield': 'raise', 'trinket': 'put on'}[slot]
        note = (f" (The {previous} goes back in your pack.)"
                if previous and previous != 'unarmed strikes' else "")
        self.log_message(f"You {verb} the {item}." + note, color='important')
        if item in MAGIC_ITEMS:
            self.log_message(MAGIC_ITEMS[item]['desc'], color='important')
        self.update_derived_stats()
        self.refresh_stats()
        self.refresh_inventory()
        return True

    def unequip_slot(self, slot):
        """Take whatever is in a slot off and put it back in the bag."""
        attr = SLOT_ATTR.get(slot)
        if not attr:
            return
        item = getattr(self, attr, None)
        if not item:
            self.log_message(f"You have nothing in your {slot} slot.")
            return
        if slot == 'weapon':
            setattr(self, attr, 'unarmed strikes')
            self.log_message(f"You stow the {item} and raise your fists.")
        else:
            setattr(self, attr, None)
            self.log_message(f"You take off the {item}.")
        if item != 'unarmed strikes':
            self.inventory.append(item)
        self.update_derived_stats()
        self.refresh_stats()
        self.refresh_inventory()

    def open_equipment_window(self):
        """The Gear screen: see all four slots at once and swap anything into them.

        This is the answer to "what am I actually wearing" - each slot shows what is
        in it, what that is doing for you, and every alternative in your bag.
        
"""
        self.open_sheet('gear')

    def _build_gear_tab(self, container):
        """Build the gear screen into its tab of the shared character window."""
        outer = container
        summary = ttk.Label(outer, text="", style='Gold.TLabel', wraplength=520, justify=tk.LEFT)
        summary.pack(anchor=tk.W, pady=(2, 8))

        body = self.make_scrollable(outer)

        def rebuild():
            for w in body.winfo_children():
                w.destroy()
            gear = self.gear_effects()
            bits = [f"AC {self.player_ac}", f"Attack +{self.player_attack_bonus}",
                    f"Damage 1d{self.player_damage_dice}+{self.player_damage_bonus}"]
            if getattr(self, 'damage_reduction', 0):
                bits.append(f"Damage reduction {self.damage_reduction}")
            if gear.get('spell_atk'):
                bits.append(f"Spell +{gear['spell_atk']}")
            if gear.get('crit_range', 20) < 20:
                bits.append(f"Crits on {gear['crit_range']}+")
            summary.configure(text='   '.join(bits))

            for slot in EQUIP_SLOTS:
                current = getattr(self, SLOT_ATTR[slot], None)
                box = ttk.LabelFrame(body, text=slot.title(), padding=8)
                box.pack(fill=tk.X, pady=(4, 4))
                head = current if current else "(nothing equipped)"
                ttk.Label(box, text=head, font=("Segoe UI", 11, "bold"),
                          style='Gold.TLabel').pack(anchor=tk.W)
                if current:
                    ttk.Label(box, text=self.describe_item(current), style='Dim.TLabel',
                              wraplength=480, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 4))
                    if not (slot == 'weapon' and current == 'unarmed strikes'):
                        ttk.Button(box, text=f"Take off the {current}",
                                   command=lambda s=slot: (self.unequip_slot(s), rebuild())
                                   ).pack(anchor=tk.W, pady=(2, 2))
                # everything in the bag that could go in this slot instead
                options = sorted({i for i in self.inventory if self.item_slot(i) == slot})
                if options:
                    ttk.Label(box, text="In your bag:", style='Dim.TLabel').pack(anchor=tk.W, pady=(4, 0))
                    for item in options:
                        ttk.Button(box, text=f"Equip {item}",
                                   command=lambda i=item: (self.equip_item(i), rebuild())
                                   ).pack(fill=tk.X, pady=2)
                elif not current:
                    ttk.Label(box, text="Nothing in your bag fits here.",
                              style='Dim.TLabel').pack(anchor=tk.W)

        rebuild()

    # ---------------------------------------------------------- using things

    def apply_item_effect(self, item):
        """Perform an item's actual effect. Returns True if it was really used.

        The return value matters: some items decline to be used (a map outside the
        dungeon, a rope you keep, a bomb with nothing to throw it at), and those must
        not cost you your bonus action.

        To add an item: add a branch here, plus entries in ITEM_INFO and ITEM_PRICES
        in data.py.
        
"""
        if self.item_slot(item):
            return self.equip_item(item)
        if item not in self.inventory:
            self.log_message("That item is not in your inventory.")
            return False

        # --- things that need a target, refused before they are spent ---
        thrown = {'oil flask', 'alchemists fire', 'acid vial', 'firebomb', 'holy water',
                  'thunderstone', 'net', 'caltrops', 'smoke bomb'}
        combat_only = thrown | {'whetstone', 'poison vial', 'blessed oil'}
        if item in combat_only and not self.in_combat:
            self.log_message(f"The {item} needs a fight to be worth anything. Save it.")
            return False
        if item in {'bandages', 'ration'} and self.in_combat:
            self.log_message(f"There is no time for {item} in the middle of a fight.")
            return False

        used = True
        self.inventory.remove(item)
        target = self.current_target() if self.in_combat else None

        # ---------------------------------------------------------- healing
        if item == 'potion':
            self.play_sound('potion')
            self.heal_player(random.randint(1, 4) + random.randint(1, 4) + 2, "You drink a potion")
        elif item == 'greater potion':
            self.play_sound('potion')
            amount = sum(random.randint(1, 4) for _ in range(4)) + 4
            self.heal_player(amount, "You drain a greater potion")
        elif item == 'superior potion':
            self.play_sound('potion')
            amount = sum(random.randint(1, 4) for _ in range(8)) + 8
            self.heal_player(amount, "You swallow a superior potion")
        elif item == 'elixir of life':
            self.play_sound('levelup')
            self.heal_player(self.max_health, "The elixir burns going down", full=True)
        elif item == 'healing herbs':
            self.heal_player(random.randint(1, 6) + 2, "You chew a handful of bitter herbs")
        elif item == 'bandages':
            self.heal_player(random.randint(1, 8) + 3, "You bind your wounds")
        elif item == 'ration':
            self.heal_player(random.randint(1, 6), "You sit down and eat properly")
        elif item == 'elixir of fortitude':
            self.temp_hp = getattr(self, 'temp_hp', 0) + 12
            self.play_sound('potion')
            self.log_message(f"Warmth spreads through your chest: {self.temp_hp} temporary HP.",
                             color='important')
        elif item in ('antidote', 'bezoar'):
            self.poisoned = 0
            if item == 'bezoar':
                self.heal_player(random.randint(1, 8), "The bezoar settles your stomach")
            self.play_sound('potion')
            self.log_message("The poison in your blood goes quiet.", color='important')

        # ---------------------------------------------------------- thrown
        elif item == 'oil flask':
            dmg = random.randint(1, 10)
            self.play_sound('hit')
            self.log_message("You hurl the flask; it bursts and catches light.")
            if target:
                self.hit_enemy(target, dmg, 'fire')
        elif item == 'alchemists fire':
            dmg = sum(random.randint(1, 6) for _ in range(2))
            self.play_sound('hit')
            self.log_message("Clinging fire splashes across your target!", color='important')
            if target:
                self.set_burning(target, 2)
                self.hit_enemy(target, dmg, 'fire')
        elif item == 'acid vial':
            dmg = sum(random.randint(1, 6) for _ in range(2))
            self.play_sound('hit')
            if target:
                target['ac'] = max(5, target['ac'] - 2)
                self.log_message(f"Acid eats into the {target['name']}'s guard (-2 AC).",
                                 color='important')
                self.hit_enemy(target, dmg, 'acid')
        elif item == 'firebomb':
            dmg = sum(random.randint(1, 6) for _ in range(3))
            self.play_sound('crit')
            self.log_message("The firebomb goes off in a wall of orange!", color='important')
            for en in list(self.living_enemies()):
                self.hit_enemy(en, dmg, 'fire')
        elif item == 'holy water':
            dmg = sum(random.randint(1, 6) for _ in range(2))
            self.play_sound('spell')
            self.log_message("Blessed water hisses where it lands.")
            if target:
                self.hit_enemy(target, dmg, 'radiant')
        elif item == 'thunderstone':
            dmg = sum(random.randint(1, 8) for _ in range(2))
            self.play_sound('crit')
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -2)
            self.log_message("The stone cracks like a thunderclap - everything reels!",
                             color='important')
            for en in list(self.living_enemies()):
                self.hit_enemy(en, dmg, 'thunder')
        elif item == 'net':
            if target:
                target['held'] = True
                self.play_sound('success')
                self.log_message(f"The net tangles the {target['name']}; it will miss its next turn.",
                                 color='important')
                self.draw_combat()
        elif item == 'caltrops':
            self.play_sound('trap_spring')
            self.log_message("You scatter caltrops across the floor.", color='important')
            for en in list(self.living_enemies()):
                self.hit_enemy(en, random.randint(1, 4), 'piercing')
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -1)
        elif item == 'smoke bomb':
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -4)
            self.smoke_cover = True
            self.play_sound('spell')
            self.log_message("Choking smoke fills the room: enemies attack at -4, and running "
                             "is suddenly a very good option.", color='important')

        # ------------------------------------------------------ combat prep
        elif item == 'whetstone':
            self.whetstone_bonus = getattr(self, 'whetstone_bonus', 0) + 2
            self.play_sound('equip')
            self.log_message("You draw the stone down your blade: +2 damage this fight.",
                             color='important')
        elif item == 'poison vial':
            self.poison_weapon = 1
            self.play_sound('spell')
            self.log_message("You coat your weapon: +1d6 poison on every hit this fight.",
                             color='important')
        elif item == 'blessed oil':
            self.radiant_weapon = 1
            self.play_sound('spell')
            self.log_message("You anoint your weapon: +1d6 radiant on every hit this fight.",
                             color='important')
        elif item == 'lucky coin':
            self.lucky_bonus = 4
            self.play_sound('coin')
            self.log_message("You flip the coin and pocket it. Your next roll gets +4.",
                             color='important')

        # --------------------------------------------------------- utility
        elif item == 'map':
            if getattr(self, 'dungeon', None):
                for r in self.dungeon['rooms'].values():
                    r['seen'] = True
                self.play_sound('success')
                self.log_message("You study the map: the layout of this floor is revealed!",
                                 color='important')
                self.draw_dungeon()
            else:
                self.inventory.append(item)  # keep it until you're in the dungeon
                self.log_message("The map shows a dungeon floor. Enter the dungeon (Explore) before using it.")
                used = False
        elif item == 'spyglass':
            self.inventory.append(item)  # reusable
            revealed = self.reveal_adjacent_rooms()
            if revealed:
                self.log_message(f"Through the spyglass you make out {revealed} room"
                                 f"{'s' if revealed != 1 else ''} beyond the doorways.",
                                 color='important')
            else:
                self.log_message("You raise the spyglass, but there is nothing new to see from here.")
                used = False
        elif item in ('rope', 'grappling hook'):
            self.inventory.append(item)  # not consumed here; springing a trap uses it up
            self.log_message(f"You coil the {item} and keep it ready. It can spring dungeon traps "
                             "from a safe distance.")
            used = False
        elif item in ('thieves tools', 'crowbar', 'climbing gear'):
            self.inventory.append(item)  # passive, always on while carried
            what = {'thieves tools': 'locks and traps',
                    'crowbar': 'anything you need to force open',
                    'climbing gear': 'climbing, vaulting and leaping'}[item]
            self.log_message(f"You keep the {item} to hand. It already helps with {what} "
                             "just by being in your bag (+3).")
            used = False
        elif item == 'shovel':
            self.inventory.append(item)
            if self.dig_here():
                pass
            else:
                self.log_message("You dig for a while and find nothing but older dirt.")
            used = False
        elif item == 'torch':
            if self.in_combat:
                self.torch_active = True
                self.log_message("You light the torch. Your next attack is easier to land.")
            else:
                self.log_message("You light the torch and see the area more clearly.")
        elif item == 'lantern':
            if self.in_combat:
                self.lantern_active = True
                self.log_message("You light the lantern. The enemy struggles to see you clearly.")
            else:
                self.log_message("The lantern brightens the path and reveals hidden details.")

        # --------------------------------------------------------- scrolls
        elif item in SCROLLS:
            spell_key, slot_level = SCROLLS[item]
            name = SPELL_CATALOG.get(spell_key, (item,))[0]
            self.log_message(f"You read the {item} aloud. The paper crumbles.", color='important')
            if not self.cast_spell(spell_key, level=slot_level, from_scroll=True):
                # the spell refused to go off, so the scroll is not wasted
                self.inventory.append(item)
                used = False
            else:
                self.log_message(f"{name} takes hold without costing you a slot.", color='important')

        # ------------------------------------------------------- valuables
        elif item in VALUABLES:
            self.inventory.append(item)
            self.log_message(f"The {item} is worth real money. Find a shop (S) and sell it.")
            used = False
        else:
            self.log_message(f"You use the {item}, but nothing obvious happens.")

        self.refresh_stats()
        self.refresh_inventory()
        self.refresh_buttons()
        return used

    def heal_player(self, amount, flavour, full=False):
        """Heal the player, respecting the max and the Beacon of Hope doubling."""
        if getattr(self, 'beacon_of_hope', False) and not full:
            amount *= 2
        healed = min(self.max_health - self.health, amount)
        self.health = min(self.max_health, self.health + healed)
        self.log_message(f"{flavour} and restore {healed} HP.",
                         color='important' if healed >= 20 else 'black')
        self.refresh_stats()
        return healed

    def reveal_adjacent_rooms(self):
        """Mark every room next to one you have walked as seen. Returns how many were new."""
        d = getattr(self, 'dungeon', None)
        if not d:
            return 0
        revealed = 0
        for pos, room in list(d['rooms'].items()):
            if not room['visited']:
                continue
            for dr in room['doors']:
                dx, dy = self.DIRS[dr]
                nxt = (pos[0] + dx, pos[1] + dy)
                if nxt in d['rooms'] and not d['rooms'][nxt]['seen']:
                    d['rooms'][nxt]['seen'] = True
                    revealed += 1
        self.draw_dungeon()
        return revealed

    def dig_here(self):
        """Dig in the current room with a shovel. Sometimes there is something under it."""
        if not getattr(self, 'dungeon', None) or self.in_combat:
            self.log_message("There is nowhere useful to dig right now.")
            return False
        floor = self.dungeon.get('floor', 1)
        roll = random.random()
        if roll < 0.30:
            gold = random.randint(8, 20) + floor * 4
            self.gold += gold
            self.play_sound('coin')
            self.log_message(f"Your shovel strikes a buried purse: {gold} gold!", color='important')
            return True
        if roll < 0.42:
            item = random.choice(COMMON_LOOT)
            self.inventory.append(item)
            self.play_sound('chest')
            self.log_message(f"Buried under the flagstones: a {item}.", color='important')
            return True
        return False

    def set_burning(self, enemy, rounds):
        """Set an enemy alight for a few rounds of damage at the top of each round."""
        if not hasattr(self, 'burning_enemies') or self.burning_enemies is None:
            self.burning_enemies = {}
        self.burning_enemies[enemy['name'] + str(id(enemy))] = [enemy, rounds]

    # ------------------------------------------------------------- the shop

    def do_shop(self):
        """Open the shop if there is one in this room."""
        if not self.shop_available:
            self.log_message("There is no shop nearby. Explore to find one.")
            return

        self.open_shop_window()

    def shop_stock(self):
        """What this merchant has today: staples, rotating gear, and deeper wares.

        The gear on offer is rolled once per floor and kept in self._shop_gear, so
        browsing away and coming back does not reroll it. Deeper floors put real
        magic items on the table.
        
"""
        floor = self.dungeon.get('floor', 1) if getattr(self, 'dungeon', None) else 1
        stock = dict(self.shop_items)
        if not getattr(self, '_shop_gear', None):
            gear_pool = [w for w in MUNDANE_WEAPONS] + list(MUNDANE_ARMOR) + list(MUNDANE_SHIELDS)
            picks = random.sample(gear_pool, min(4, len(gear_pool)))
            # merchants this far down have found things worth keeping
            rarities = ['Uncommon']
            if floor >= 3:
                rarities.append('Rare')
            if floor >= 7:
                rarities.append('Very Rare')
            magic_pool = [m for r in rarities for m in MAGIC_BY_RARITY.get(r, [])]
            if magic_pool and random.random() < min(0.85, 0.35 + floor * 0.08):
                picks += random.sample(magic_pool, min(2, len(magic_pool)))
            self._shop_gear = picks
        for name in self._shop_gear:
            stock[name] = self.item_price(name)
        return stock

    def open_shop_window(self):
        """The shop: buy supplies, weapons, armour and magic items, and sell your loot."""
        shop_window = self.make_popup("Traveling Shop")

        outer = ttk.Frame(shop_window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Traveling Shop", font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)
        gold_label = ttk.Label(outer, text=f"Gold: {self.gold}", style='Gold.TLabel')
        gold_label.pack(anchor=tk.W, pady=(2, 6))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)
        buy_tab = ttk.Frame(notebook, padding=8)
        sell_tab = ttk.Frame(notebook, padding=8)
        notebook.add(buy_tab, text="Buy")
        notebook.add(sell_tab, text="Sell")

        def scrollable(parent):
            canvas = tk.Canvas(parent, highlightthickness=0, bg=self.PAL['bg'])
            bar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
            canvas.configure(yscrollcommand=bar.set)
            bar.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            inner = ttk.Frame(canvas)
            canvas.create_window((0, 0), window=inner, anchor="nw")
            inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            return inner

        buy_body = scrollable(buy_tab)
        sell_body = scrollable(sell_tab)

        def refresh_gold():
            try:
                if gold_label.winfo_exists():
                    gold_label.configure(text=f"Gold: {self.gold}")
            except Exception:
                pass

        def build_sell():
            for w in sell_body.winfo_children():
                w.destroy()
            sellable = [(i, c) for i, c in self.inventory_stacks() if self.item_price(i) > 0]
            if not sellable:
                ttk.Label(sell_body, text="You have nothing the merchant wants.").pack(anchor=tk.W)
                return
            ttk.Label(sell_body, text=f"The merchant pays {int(SELL_RATE * 100)}% of value.",
                      style='Dim.TLabel').pack(anchor=tk.W, pady=(0, 6))
            for item, count in sellable:
                price = max(1, int(self.item_price(item) * SELL_RATE))
                row = ttk.Frame(sell_body)
                row.pack(fill=tk.X, pady=2)
                label = item if count == 1 else f"{item}  x{count}"
                ttk.Label(row, text=label, width=30).pack(side=tk.LEFT)
                ttk.Button(row, text=f"Sell ({price}g)",
                           command=lambda i=item: (self.sell_item(i), refresh_gold(), build_sell())
                           ).pack(side=tk.RIGHT)

        def build_buy():
            for w in buy_body.winfo_children():
                w.destroy()
            stock = self.shop_stock()
            groups = {'Supplies': [], 'Gear': [], 'Magic': []}
            for item, cost in stock.items():
                if item in MAGIC_ITEMS:
                    groups['Magic'].append((item, cost))
                elif self.item_slot(item):
                    groups['Gear'].append((item, cost))
                else:
                    groups['Supplies'].append((item, cost))
            for title, entries in groups.items():
                if not entries:
                    continue
                box = ttk.LabelFrame(buy_body, text=title, padding=6)
                box.pack(fill=tk.X, pady=(4, 4))
                for item, cost in entries:
                    row = ttk.Frame(box)
                    row.pack(fill=tk.X, pady=2)
                    if item in WEAPONS:
                        die, mod, _ = WEAPONS[item]
                        sign = '+' if mod > 0 else ''
                        desc = f"{item.title()} (d{die}{f', {sign}{mod} atk' if mod else ''})"
                    elif item in ARMOR:
                        desc = f"{item.title()} (+{ARMOR[item][0]} AC)"
                    elif item in SHIELDS:
                        desc = f"{item.title()} (+{SHIELDS[item][0]} AC, shield)"
                    elif item in MAGIC_ITEMS:
                        desc = f"{item.title()} ({MAGIC_ITEMS[item]['slot']})"
                    else:
                        desc = item.title()
                    ttk.Label(row, text=desc, width=34).pack(side=tk.LEFT)
                    ttk.Label(row, text=f"{cost}g", width=7, style='Gold.TLabel').pack(side=tk.LEFT)
                    ttk.Button(row, text="Buy",
                               command=lambda i=item, c=cost: (
                                   self.buy_shop_item(i, c, shop_window, gold_label),
                                   build_sell())
                               ).pack(side=tk.RIGHT)
                    if item in MAGIC_ITEMS:
                        ttk.Label(box, text=MAGIC_ITEMS[item]['desc'], style='Dim.TLabel',
                                  wraplength=440, justify=tk.LEFT).pack(anchor=tk.W, padx=(6, 0))

        build_buy()
        build_sell()
        # merchants know people: one companion for hire, if you travel alone
        if not getattr(self, 'companion', None):
            hire_bar = ttk.Frame(outer)
            hire_bar.pack(fill=tk.X, pady=(8, 0))
            ttk.Label(hire_bar, text="The merchant knows a few blades looking for work.",
                      style='Dim.TLabel').pack(side=tk.LEFT)
            ttk.Button(hire_bar, text="Hire a Companion...",
                       command=lambda: self.open_hire_menu(shop_window, refresh_gold)
                       ).pack(side=tk.RIGHT)
        ttk.Button(outer, text="Leave Shop", command=shop_window.destroy).pack(pady=(10, 0))

    def sell_item(self, item):
        """Sell one of an item at the merchant's rate."""
        if item not in self.inventory:
            return
        price = max(1, int(self.item_price(item) * SELL_RATE))
        self.inventory.remove(item)
        self.gold += price
        self.play_sound('coin')
        self.log_message(f"You sell the {item} for {price} gold.")
        self.refresh_stats()
        self.refresh_inventory()

    def buy_shop_item(self, item, cost, window, gold_label=None):
        """Complete a purchase if you can afford it. Keeps the shop open and updates the gold label."""
        if self.gold < cost:
            self.log_message(f"You need {cost} gold to buy a {item}.")
            return

        self.play_sound('coin')
        self.gold -= cost
        self.inventory.append(item)
        self.log_message(f"You buy a {item} for {cost} gold.", color='important')
        if item in MAGIC_ITEMS:
            # one-of-a-kind stock: the merchant does not have a second one
            try:
                self._shop_gear = [g for g in getattr(self, '_shop_gear', []) if g != item]
            except Exception:
                pass
        self.refresh_stats()
        self.refresh_inventory()

        # update displayed gold in the shop without closing it
        try:
            if gold_label and gold_label.winfo_exists():
                gold_label.configure(text=f"Gold: {self.gold}")
        except Exception:
            pass

        self.place_window(shop_window, min_w=600, min_h=520)

    def do_heal(self):
        """Buy a quick heal for 5 gold, outside the shop."""
        if self.gold >= 5:
            self.gold -= 5
            self.heal_player(25, "You spend 5 gold on a healing potion")
        else:
            self.log_message("You need at least 5 gold to heal.")
        self.refresh_stats()

    def roll_loot(self, floor, magic_chance=0.0, rarity=None, deep=False):
        """Pick one random item appropriate to how deep you are.

        magic_chance is the odds of a magic item instead of a supply; rarity forces a
        specific tier (bosses use this). Deeper floors quietly shift the pool towards
        DEEP_LOOT on their own.
        
"""
        if rarity:
            pool = MAGIC_BY_RARITY.get(rarity) or MAGIC_BY_RARITY['Uncommon']
            return random.choice(pool)
        if magic_chance and random.random() < magic_chance:
            tiers = ['Uncommon']
            if floor >= 4:
                tiers.append('Rare')
            if floor >= 8:
                tiers.append('Very Rare')
            if floor >= 12:
                tiers.append('Legendary')
            pool = [m for t in tiers for m in MAGIC_BY_RARITY.get(t, [])]
            if pool:
                return random.choice(pool)
        if deep or random.random() < min(0.5, 0.08 * floor):
            return random.choice(DEEP_LOOT)
        return random.choice(COMMON_LOOT)
