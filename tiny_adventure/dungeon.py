"""The dungeon: floor generation, the crawl window, and what is in each room.

HOW A FLOOR IS BUILT
generate_floor() carves a grid of connected rooms, then decorates them: a
start room, stairs down placed as far from the start as possible, and the rest
seeded with enemies, traps, chests, mysteries, shops and camps.

self.dungeon is a plain dict:

    floor   which level down you are
    size    grid width/height
    pos     (x, y) of the room you are standing in
    rooms   {(x, y): room_dict}

Each room dict records its type, its exits, whether you have seen it, and
whether its encounter has already been used up.

MOVING AND ENCOUNTERS
move_player() walks you between rooms; enter_dungeon_room() fires whatever is
in the new one. The encounter_* methods each open a small decision dialog -
they are the most self-contained code in the game and the easiest place to add
new content.

WALKING INTO SOMETHING HOSTILE puts you straight into combat. There is no
"press Attack to begin" step: the dungeon window closes and the fight starts.
Roll badly on the surprise check and they get the first round. If it goes
wrong, Flee (in combat.py) backs you out to the room you came from, which is
what self._last_pos is recorded for.

BOSS FLOORS
Every BOSS_EVERY floors the stairs are guarded: the far room is type 'boss'
instead of 'stairs', and only turns back into stairs once you have won. That
is handled by on_combat_victory below, which combat.py calls when a fight
ends with everything dead.

WHERE TO CHANGE THINGS

    Floor size and layout ......... generate_floor
    How common each room type is .. generate_floor (the weighted choices)
    Trap/chest/mystery outcomes ... encounter_trap / _chest / _mystery
    Add a new room type ........... generate_floor, then enter_dungeon_room
    The map display ............... draw_dungeon
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (WEAPONS, FINESSE, ARMOR, SHIELDS, MAGIC_ITEMS, CLASSES,
                   DIFFICULTIES, CLASS_SPELLS, BOSSES, BOSS_EVERY,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, SPELL_CATALOG, COMMON_LOOT, DEEP_LOOT,
                   MUNDANE_WEAPONS, MUNDANE_ARMOR, MUNDANE_SHIELDS)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class DungeonMixin:

    DIRS = {'N': (0, -1), 'S': (0, 1), 'W': (-1, 0), 'E': (1, 0)}

    OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}

    def do_explore(self):
        """Open the dungeon crawl window (generating floor 1 if needed)."""
        # Prevent leaving or opening the dungeon while a fight is ongoing or pending
        if self.in_combat or getattr(self, 'enemy_attack_pending', False) or getattr(self, 'current_event', None) == 'enemy' or getattr(self, 'enemies', []):
            self.log_message("You cannot explore while in combat or when enemies are active. Finish the fight first.")
            return
        if getattr(self, 'dungeon_window_open', False):
            self.dungeon_window.lift()
            return
        if not getattr(self, 'dungeon', None):
            self.generate_floor(1)
            self.log_message("You descend into the dungeon...", color="important")
        self.open_dungeon_window()

    def generate_floor(self, floor):
        """Build a new floor: carve connected rooms, then fill them with content.

        Deeper floors are larger and more dangerous. Stairs go as far from the start
        as the layout allows, so a floor always takes some exploring.
        
"""
        size = 5
        rooms = {}
        for y in range(size):
            for x in range(size):
                rooms[(x, y)] = {'type': 'empty', 'visited': False, 'seen': False, 'doors': []}

        # Carve a maze with randomized depth-first search: every room is
        # reachable, but walls create real dead ends and winding paths.
        stack = [(0, 0)]
        carved = {(0, 0)}
        while stack:
            cx, cy = stack[-1]
            options = []
            for d, (dx, dy) in self.DIRS.items():
                nxt = (cx + dx, cy + dy)
                if nxt in rooms and nxt not in carved:
                    options.append((d, nxt))
            if options:
                d, nxt = random.choice(options)
                rooms[(cx, cy)]['doors'].append(d)
                rooms[nxt]['doors'].append(self.OPPOSITE[d])
                carved.add(nxt)
                stack.append(nxt)
            else:
                stack.pop()

        # Knock a few extra doors through so the maze has loops (more choices)
        for _ in range(4):
            x, y = random.randint(0, size - 1), random.randint(0, size - 1)
            d = random.choice(list(self.DIRS))
            dx, dy = self.DIRS[d]
            nxt = (x + dx, y + dy)
            if nxt in rooms and d not in rooms[(x, y)]['doors']:
                rooms[(x, y)]['doors'].append(d)
                rooms[nxt]['doors'].append(self.OPPOSITE[d])

        # Entrance at top-left; the way down sits in the farthest room from it.
        # On a boss floor that room holds the boss instead, and only becomes
        # stairs once the boss is dead.
        rooms[(0, 0)]['type'] = 'start'
        far = self.farthest_room(rooms, (0, 0))
        boss_floor = (floor % BOSS_EVERY == 0)
        rooms[far]['type'] = 'boss' if boss_floor else 'stairs'

        # Fill the remaining rooms with encounters
        for pos, room in rooms.items():
            if room['type'] != 'empty':
                continue
            r = random.random()
            if r < 0.28:
                room['type'] = 'enemy'
            elif r < 0.40:
                room['type'] = 'trap'
            elif r < 0.50:
                room['type'] = 'treasure'
            elif r < 0.58:
                room['type'] = 'chest'
            elif r < 0.64:
                room['type'] = 'shop'
            elif r < 0.70:
                room['type'] = 'camp'
            elif r < 0.80:
                room['type'] = 'mystery'
            # else: stays empty

        rooms[(0, 0)]['visited'] = True
        rooms[(0, 0)]['seen'] = True
        self.dungeon = {'floor': floor, 'size': size, 'pos': (0, 0), 'rooms': rooms,
                        'boss_floor': boss_floor, 'boss_defeated': False}
        self._last_pos = (0, 0)
        if boss_floor:
            self.log_message(f"Something very large is breathing somewhere on floor {floor}. "
                             "It is between you and the stairs.", color='warning')

    def farthest_room(self, rooms, start):
        """Breadth-first search: return the room farthest from start."""
        from collections import deque
        dist = {start: 0}
        queue = deque([start])
        far = start
        while queue:
            cur = queue.popleft()
            if dist[cur] > dist[far]:
                far = cur
            for d in rooms[cur]['doors']:
                dx, dy = self.DIRS[d]
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt in rooms and nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    queue.append(nxt)
        return far

    def open_dungeon_window(self):
        """Open the dungeon crawl window and bind the movement keys."""
        d = self.dungeon
        cell, pad = 70, 14
        w = d['size'] * cell + pad * 2
        self.dungeon_window = tk.Toplevel(self.root)
        self.dungeon_window.title("Dungeon Crawl")
        self.dungeon_window.transient(self.root)
        self.dungeon_window_open = True

        self.dungeon_floor_label = ttk.Label(self.dungeon_window, font=("Segoe UI", 12, "bold"))
        self.dungeon_floor_label.pack(pady=(8, 2))
        self.dungeon_canvas = tk.Canvas(self.dungeon_window, width=w, height=w, bg='#3e3e3e', highlightthickness=0)
        self.dungeon_canvas.pack(padx=8, pady=4)

        # movement pad: N on top, W/E in the middle, S below
        pad_frame = ttk.Frame(self.dungeon_window)
        pad_frame.pack(pady=(4, 4))
        ttk.Button(pad_frame, text="North", width=8, command=lambda: self.move_player('N')).grid(row=0, column=1, padx=2, pady=2)
        ttk.Button(pad_frame, text="West", width=8, command=lambda: self.move_player('W')).grid(row=1, column=0, padx=2, pady=2)
        ttk.Button(pad_frame, text="East", width=8, command=lambda: self.move_player('E')).grid(row=1, column=2, padx=2, pady=2)
        ttk.Button(pad_frame, text="South", width=8, command=lambda: self.move_player('S')).grid(row=2, column=1, padx=2, pady=2)

        ttk.Label(self.dungeon_window,
                  text="Arrow keys / WASD to move.  ? = unexplored room.\n"
                       "! enemy   ^ trap   $ treasure   # chest   S shop   C camp\n"
                       "* mystery   B BOSS   v stairs      Walking into an enemy starts the fight.",
                  justify=tk.CENTER).pack(pady=(0, 8))

        # keyboard movement
        keymap = {'w': 'N', 'a': 'W', 's': 'S', 'd': 'E',
                  'Up': 'N', 'Left': 'W', 'Down': 'S', 'Right': 'E'}
        for key, dirn in keymap.items():
            self.dungeon_window.bind(f"<KeyPress-{key}>", lambda e, dd=dirn: self.move_player(dd))
        self.dungeon_window.focus_set()

        def on_close():
            self.dungeon_window_open = False
            try:
                self.dungeon_window.destroy()
            except Exception:
                pass
        self.dungeon_window.protocol('WM_DELETE_WINDOW', on_close)
        self.draw_dungeon()
        self.place_window(self.dungeon_window)

    def close_dungeon_window(self):
        """Close the dungeon window if it is open."""
        if getattr(self, 'dungeon_window_open', False):
            self.dungeon_window_open = False
            try:
                self.dungeon_window.destroy()
            except Exception:
                pass

    def draw_dungeon(self):
        """Redraw the floor map: rooms you have seen, your position, and exits.

        Unvisited rooms stay hidden until you enter them or read a map item.
        
"""
        if not getattr(self, 'dungeon_window_open', False):
            return
        d = self.dungeon
        c = self.dungeon_canvas
        c.delete('all')
        p = self.PAL
        cell, pad = 70, 14
        colors = {'start': '#90caf9', 'empty': '#e8e4d8', 'enemy': '#ef9a9a', 'trap': '#e57373',
                  'treasure': '#ffe082', 'chest': '#bcaaa4', 'shop': '#fff59d', 'camp': '#bcaaa4',
                  'mystery': '#ce93d8', 'stairs': '#9575cd', 'boss': '#f0c419'}
        labels = {'start': 'IN', 'empty': '', 'enemy': '!', 'trap': '^', 'treasure': '$',
                  'chest': '#', 'shop': 'S', 'camp': 'C', 'mystery': '*', 'stairs': 'v',
                  'boss': 'B'}

        # a room is "adjacent" if a visited room has a door to it
        adjacent = set()
        for pos, room in d['rooms'].items():
            if not room['visited']:
                continue
            for dr in room['doors']:
                dx, dy = self.DIRS[dr]
                adjacent.add((pos[0] + dx, pos[1] + dy))

        self.dungeon_floor_label.configure(text=f"Dungeon Floor {d['floor']}")
        for pos, room in d['rooms'].items():
            x0 = pad + pos[0] * cell
            y0 = pad + pos[1] * cell
            x1, y1 = x0 + cell, y0 + cell
            if room['visited']:
                fill, text = colors.get(room['type'], '#e8e4d8'), labels.get(room['type'], '')
            elif room['seen']:
                # revealed by the map item: show the type, but dimmed
                fill, text = '#9e9e9e', labels.get(room['type'], '')
            elif pos in adjacent:
                fill, text = '#757575', '?'
            else:
                fill, text = '#4a4a4a', ''
            c.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, fill=fill, outline='')
            if text:
                c.create_text((x0 + x1) // 2, (y0 + y1) // 2, text=text, font=("Segoe UI", 16, "bold"))
            # draw bold walls where there is no door, and doorway notches where there is
            for dr, (wx0, wy0, wx1, wy1) in (('N', (x0, y0, x1, y0)), ('S', (x0, y1, x1, y1)),
                                             ('W', (x0, y0, x0, y1)), ('E', (x1, y0, x1, y1))):
                mx, my = (wx0 + wx1) // 2, (wy0 + wy1) // 2
                if dr not in room['doors']:
                    c.create_line(wx0, wy0, wx1, wy1, fill=p['accent'], width=6)
                elif room['visited'] or room['seen'] or pos in adjacent:
                    # a visible doorway gap so exits stand out at a glance
                    if dr in ('N', 'S'):
                        c.create_rectangle(mx - 9, my - 3, mx + 9, my + 3, fill='#d8cfa8', outline='')
                    else:
                        c.create_rectangle(mx - 3, my - 9, mx + 3, my + 9, fill='#d8cfa8', outline='')

        # highlight current position
        px, py = d['pos']
        x0 = pad + px * cell
        y0 = pad + py * cell
        c.create_rectangle(x0 + 4, y0 + 4, x0 + cell - 4, y0 + cell - 4, outline='#1565c0', width=3)

    def move_player(self, direction):
        """Walk one room in a direction, if there is an exit that way."""
        if self.in_combat or not getattr(self, 'dungeon_window_open', False):
            return
        d = self.dungeon
        room = d['rooms'][d['pos']]
        if direction not in room['doors']:
            dx, dy = self.DIRS[direction]
            over = (d['pos'][0] + dx, d['pos'][1] + dy)
            if getattr(self, 'levitate_charge', False) and over in d['rooms']:
                self.levitate_charge = False
                self.log_message("You float up and over the wall!", color='important')
            else:
                self.log_message("A solid wall blocks the way.")
                return
        dx, dy = self.DIRS[direction]
        # remembered so that fleeing a fight can back you out the way you came
        self._last_pos = d['pos']
        d['pos'] = (d['pos'][0] + dx, d['pos'][1] + dy)
        self.play_sound('door')
        new_room = d['rooms'][d['pos']]
        first_visit = not new_room['visited']
        new_room['visited'] = True
        new_room['seen'] = True
        # leaving a room clears location-bound states
        self.can_long_rest = False
        self.shop_available = False
        if self.current_event in ('shop', 'camp'):
            self.current_event = None
        self.draw_dungeon()
        self.enter_dungeon_room(new_room, first_visit)
        self.refresh_stats()
        self.refresh_inventory()
        self.refresh_buttons()

    def enter_dungeon_room(self, room, first_visit):
        """Trigger whatever is in a room you just walked into."""
        floor = self.dungeon['floor']
        rtype = room['type']

        if rtype in ('start', 'empty'):
            if first_visit:
                self.log_message(random.choice([
                    "The room is empty save for dust and old bones.",
                    "Water drips somewhere in the darkness. Nothing stirs.",
                    "Faded carvings cover the walls, but the room is empty.",
                ]))
            return

        if rtype == 'enemy':
            room['type'] = 'empty'  # the enemies leave their lair to fight you
            self._fled_room_type = 'enemy'
            self.pending_enemies = self.make_enemy_pack(floor)
            self.begin_encounter()
            return

        if rtype == 'boss':
            self._fled_room_type = 'boss'
            self.pending_enemies = self.make_boss(floor)
            self.begin_encounter(boss=True)
            return

        if rtype == 'treasure':
            room['type'] = 'empty'
            gold = random.randint(8, 16) + (floor - 1) * 4
            self.gold += gold
            self.play_sound('coin')
            self.log_message(f"You find a small hoard: {gold} gold!", color='important')
            if random.random() < 0.5:
                item = self.roll_loot(floor, magic_chance=0.06)
                self.inventory.append(item)
                self.log_message(f"Tucked beneath the coins is a {item}.", color='important')
            return

        if rtype == 'chest':
            self.encounter_chest(room, floor)
            return

        if rtype == 'trap':
            self.encounter_trap(room, floor)
            return

        if rtype == 'shop':
            self.current_event = 'shop'
            self.shop_available = True
            self.log_message("A hooded merchant has set up shop in this room. Use the Shop button to trade.", color='important')
            return

        if rtype == 'camp':
            self.current_event = 'camp'
            self.can_long_rest = True
            self.log_message("An abandoned campsite with a firepit. You may Long Rest here safely.", color='important')
            return

        if rtype == 'mystery':
            self.encounter_mystery(room, floor)
            return

        if rtype == 'stairs':
            self.open_decision(
                "Stairs Down",
                f"A dark stairwell descends to floor {floor + 1}.\n"
                "Deeper floors hold stronger enemies and richer treasure.\n"
                "There is no way back up.",
                [("Descend", lambda: self.descend_stairs()),
                 ("Stay on this floor", None)])
            return

    def begin_encounter(self, boss=False):
        """Walk into something hostile and the fight starts immediately.

        There is no "press Attack to begin" any more. You get a surprise check
        first: lose it and the enemies take the opening round while you are still
        drawing your weapon.
        
"""
        self.current_event = 'enemy'
        self.play_sound('enemy_hit')
        names = ', '.join(e['name'] for e in self.pending_enemies)
        if boss:
            self.log_message("The door swings shut behind you.", color='enemy')
        elif len(self.pending_enemies) == 1:
            self.log_message(f"A {names} lunges out of the shadows!", color='enemy')
        else:
            self.log_message(f"Enemies block your path: {names}!", color='enemy')
        self.close_dungeon_window()

        # surprise: a bad roll hands them the first round
        surprised = False
        if not boss:
            dc = 9 + self.current_floor()
            roll = random.randint(1, 20) + self.ability_mod('wisdom') + self.check_bonus()
            surprised = roll < dc
            if surprised:
                self.log_message(f"They were waiting for you ({roll} vs DC {dc}) \u2014 "
                                 "they get the first move!", color='warning')
            else:
                self.log_message(f"You spot them in time ({roll} vs DC {dc}).", color='player')

        self.do_attack()
        if surprised and self.in_combat:
            self.player_action_available = False
            self.player_bonus_available = False
            self.enemy_attack_pending = True
            self.refresh_buttons()
            self.root.after(600, self.resolve_enemy_attack)

    def on_combat_victory(self):
        """Called by combat.py the moment a fight ends with everything dead.

        Its one job is turning a cleared boss room into the stairs down, so that
        beating the boss is what actually opens the way deeper.
        
"""
        d = getattr(self, 'dungeon', None)
        self._fled_room_type = None
        if not d:
            return
        room = d['rooms'].get(d['pos'])
        if room is not None and room['type'] == 'boss':
            room['type'] = 'stairs'
            d['boss_defeated'] = True
            self.log_message("Behind where it stood, a stairwell drops away into the dark. "
                             "The way down is open.", color='important')
            self.draw_dungeon()

    def descend_stairs(self):
        """Take the stairs down and generate the next floor."""
        self._shop_gear = []  # merchants on new floors carry new gear
        self._fled_room_type = None
        new_floor = self.dungeon['floor'] + 1
        self.generate_floor(new_floor)
        self.play_sound('success')
        self.log_message(f"You descend to dungeon floor {new_floor}. The air grows colder...", color='important')
        self.draw_dungeon()

    def check_bonus(self, tool=None):
        """Everything that helps an ability check: gear, tools in your bag, Guidance.

        Pass a tool name ('thieves tools', 'crowbar', 'climbing gear') to add its +3
        if you are carrying it. This is why buying tools is worth doing - they work
        from inside the bag without being used up.
        
"""
        bonus = self.gear_effects().get('check_bonus', 0)
        bonus += getattr(self, 'check_bonus_temp', 0)
        if tool and tool in self.inventory:
            bonus += 3
        if getattr(self, 'guidance_ready', False):
            bonus += random.randint(1, 4)
        if getattr(self, 'lucky_bonus', 0):
            bonus += self.lucky_bonus
        return bonus

    def skill_check(self, stat_name, dc, tool=None):
        """Roll d20 + ability modifier vs a difficulty class. Logs and returns success.

        Gear, tools and Guidance are folded in by check_bonus, and any one-shot
        bonuses (a lucky coin, a Guidance cantrip) are spent by making the roll.
        
"""
        mod = self.ability_mod(stat_name.lower())
        extra = self.check_bonus(tool)
        roll = random.randint(1, 20)
        self.show_dice_roll(roll)
        total = roll + mod + extra
        # one-shot helpers are used up by the attempt, win or lose
        if getattr(self, 'guidance_ready', False):
            self.guidance_ready = False
        if getattr(self, 'lucky_bonus', 0):
            self.lucky_bonus = 0
        outcome = "Success!" if total >= dc else "Failure."
        note = f" (+{extra} from gear and tools)" if extra else ""
        self.log_message(f"{stat_name.upper()} check: {roll} {mod:+d} = {total} vs DC {dc}{note}. {outcome}")
        return total >= dc

    def open_decision(self, title, text, choices):
        """Show a modal decision dialog. choices = list of (label, callback or None)."""
        win = self.make_popup(title)
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text=title, font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(frm, text=text, justify=tk.LEFT, wraplength=340).pack(anchor=tk.W, pady=(6, 10))

        def pick(cb):
            win.destroy()
            if cb:
                cb()
            self.draw_dungeon()
            self.refresh_stats()
            self.refresh_inventory()
            self.refresh_buttons()

        for label, cb in choices:
            ttk.Button(frm, text=label, command=lambda c=cb: pick(c)).pack(fill=tk.X, pady=3)
        self.place_window(win, min_w=420, min_h=220)

    def take_dungeon_damage(self, amount, reason):
        """Take damage outside combat, handling death if it kills you.

        Routed through damage_player so that temporary HP, damage reduction and a
        Death Ward all work against traps and bad decisions, not just monsters.
        
"""
        self.damage_player(amount, reason)
        if self.health <= 0:
            self.close_dungeon_window()
            self.handle_death()
        else:
            self.refresh_stats()

    def encounter_trap(self, room, floor):
        """A trap: spring it, disarm it, leap it, or use a rope from a safe distance."""
        if getattr(self, 'mage_hand_ready', False):
            self.mage_hand_ready = False
            room['type'] = 'empty'
            self.play_sound('success')
            self.log_message("Your spectral hand darts ahead and springs the trap harmlessly!", color='important')
            return
        kinds = [('dart trap', 'dexterity', 'Darts hiss from the walls!'),
                 ('pit trap', 'endurance', 'The floor gives way beneath you!'),
                 ('gas trap', 'constitution', 'Green gas floods the room!')]
        name, save_stat, trigger_text = random.choice(kinds)
        dc = 11 + floor
        damage = random.randint(4, 8) + (floor - 1) * 2

        def spring():
            room['type'] = 'empty'
            self.play_sound('trap_spring')
            if self.skill_check(save_stat, dc):
                half = max(1, damage // 2)
                self.take_dungeon_damage(half, f"{trigger_text} You partially avoid it.")
            else:
                self.take_dungeon_damage(damage, trigger_text)

        # spotting the trap is a Dexterity (perception-style) check
        self.log_message("Something feels wrong about this room... (spot check)")
        if not self.skill_check('dexterity', dc - 2, tool='thieves tools'):
            self.log_message("You notice the trap a moment too late!", color='warning')
            spring()
            return

        def disarm():
            if self.skill_check('dexterity', dc, tool='thieves tools'):
                room['type'] = 'empty'
                self.play_sound('success')
                xp = 8 + floor * 4
                self.add_xp(xp)
                self.log_message(f"You carefully disarm the {name}.", color='important')
            else:
                spring()

        def leap():
            if self.skill_check('endurance', dc - 2, tool='climbing gear'):
                room['type'] = 'empty'
                self.play_sound('success')
                self.log_message(f"You vault cleanly past the {name}.", color='important')
            else:
                spring()

        def use_line(tool):
            if tool in self.inventory:
                self.inventory.remove(tool)
                room['type'] = 'empty'
                self.play_sound('success')
                self.log_message(f"You trigger the {name} from a safe distance with your {tool}. "
                                 f"The {tool} does not survive it.", color='important')
            else:
                self.log_message(f"You don't have a {tool}.")
                self.encounter_trap(room, floor)  # reopen choices

        tools_note = " (+3 with thieves tools)" if 'thieves tools' in self.inventory else ""
        climb_note = " (+3 with climbing gear)" if 'climbing gear' in self.inventory else ""
        choices = [(f"Disarm it (DEX check, DC {dc}){tools_note}", disarm),
                   (f"Leap past it (END check, DC {dc - 2}){climb_note}", leap)]
        for line in ('rope', 'grappling hook'):
            if line in self.inventory:
                choices.append((f"Spring it safely with your {line} (uses the {line})",
                                lambda t=line: use_line(t)))
        self.open_decision("Trap!", f"You spot a {name} guarding the room.\nHow do you get past?", choices)

    def encounter_chest(self, room, floor):
        """A chest: open it, pick the lock, or force it open."""
        pick_dc = 11 + floor
        smash_dc = 12 + floor
        if getattr(self, 'char_class', None) == 'Rogue':
            pick_dc -= 3  # rogues are natural lockpicks

        def loot():
            room['type'] = 'empty'
            self.play_sound('chest')
            gold = random.randint(12, 22) + (floor - 1) * 5
            self.gold += gold
            gear_pool = list(MUNDANE_WEAPONS) + list(MUNDANE_ARMOR) + list(MUNDANE_SHIELDS)
            haul = [self.roll_loot(floor, magic_chance=0.12, deep=True)]
            if random.random() < 0.5:
                haul.append(random.choice(gear_pool))
            for item in haul:
                self.inventory.append(item)
            self.play_sound('coin')
            self.log_message(f"The chest opens! Inside: {gold} gold, and {' and a '.join(haul)}.",
                             color='important')

        def pick_lock():
            if self.skill_check('dexterity', pick_dc, tool='thieves tools'):
                loot()
            else:
                self.log_message("The lock resists your attempts. You could try again or force it.")

        def smash():
            if self.skill_check('strength', smash_dc, tool='crowbar'):
                loot()
            else:
                self.take_dungeon_damage(3, "You wrench your shoulder on the sturdy chest.")

        pick_note = " (+3 with thieves tools)" if 'thieves tools' in self.inventory else ""
        smash_note = " (+3 with a crowbar)" if 'crowbar' in self.inventory else ""
        self.open_decision(
            "Locked Chest",
            "A heavy ironbound chest sits in the corner, locked tight.",
            [(f"Pick the lock (DEX, DC {pick_dc}){pick_note}", pick_lock),
             (f"Smash it open (STR, DC {smash_dc}){smash_note}", smash),
             ("Leave it", None)])

    def encounter_mystery(self, room, floor):
        """A random oddity - a fountain, an altar, a lever. Outcomes vary."""
        event = random.choice(['fountain', 'skeleton', 'lever', 'shrine'])
        room['type'] = 'empty'

        if event == 'fountain':
            def drink():
                r = random.random()
                if r < 0.5:
                    heal = min(self.max_health - self.health, 20)
                    self.health += heal
                    self.play_sound('potion')
                    self.log_message(f"The water is pure! You recover {heal} HP.", color='important')
                elif r < 0.75:
                    self.take_dungeon_damage(8, "The water is foul!")
                else:
                    gold = 10 + floor * 3
                    self.gold += gold
                    self.play_sound('coin')
                    self.log_message(f"Coins glitter at the bottom! You fish out {gold} gold.", color='important')
                self.refresh_stats()
            def bottle():
                self.inventory.append('potion')
                self.log_message("You bottle some of the strange water. (+1 potion)")
            self.open_decision("Ancient Fountain",
                               "A stone fountain still trickles with faintly glowing water.",
                               [("Drink from it", drink), ("Bottle some", bottle), ("Leave it", None)])

        elif event == 'skeleton':
            def loot():
                if random.random() < 0.65:
                    gold = 6 + floor * 3
                    self.gold += gold
                    item = self.roll_loot(floor, magic_chance=0.08)
                    self.inventory.append(item)
                    self.play_sound('coin')
                    self.log_message(f"You find {gold} gold and a {item} on the remains.", color='important')
                else:
                    self.take_dungeon_damage(5 + floor, "A needle trap on the belt pouch pricks you!")
            def pray():
                xp = 6 + floor * 3
                self.add_xp(xp)
                self.log_message("You lay the adventurer to rest. You feel wiser for it.")
            self.open_decision("Fallen Adventurer",
                               "The skeleton of an unlucky adventurer slumps against the wall,\n"
                               "a bulging belt pouch still on its hip.",
                               [("Search the remains", loot), ("Give them last rites", pray), ("Leave quietly", None)])

        elif event == 'lever':
            def pull():
                if random.random() < 0.5:
                    gold = 10 + floor * 4
                    self.gold += gold
                    self.play_sound('success')
                    self.log_message(f"A hidden panel slides open: {gold} gold inside!", color='important')
                else:
                    self.play_sound('enemy_hit')
                    self.log_message("A grinding noise echoes... something is coming!", color='warning')
                    room['type'] = 'enemy'
                    self.enter_dungeon_room(room, True)
            self.open_decision("Mysterious Lever",
                               "A rusted iron lever juts from the wall. It practically begs to be pulled.",
                               [("Pull it", pull), ("Absolutely not", None)])

        else:  # shrine
            def donate():
                if self.gold >= 5:
                    self.gold -= 5
                    if random.random() < 0.5:
                        heal = min(self.max_health - self.health, 15)
                        self.health += heal
                        self.play_sound('levelup')
                        self.log_message(f"Warm light washes over you. You recover {heal} HP.", color='important')
                    else:
                        xp = 10 + floor * 4
                        self.add_xp(xp)
                        self.log_message("The shrine hums approvingly. You feel enlightened.", color='important')
                else:
                    self.log_message("You don't have 5 gold to offer.")
                self.refresh_stats()
            self.open_decision("Forgotten Shrine",
                               "A small shrine to a forgotten god, its offering bowl empty.",
                               [("Offer 5 gold", donate), ("Move on", None)])
