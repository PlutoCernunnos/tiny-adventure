"""Combat: turn order, attacks, the action economy, bosses, and running away.

HOW A ROUND WORKS - this is the heart of the file

    1. do_attack()          starts the fight (enemies appear, you get a turn)
    2. you act, as often as your action economy allows:
           an ACTION       - one attack, or one 'action' spell
           a BONUS ACTION  - off-hand jab, defend, or using an item
       Attacking does NOT end your turn. Nothing happens on the enemy side
       until you choose to end it.
    3. end_turn()           you hand over deliberately
    4. _enemy_turn_step()   each enemy attacks in turn, staggered by a timer
    5. start_of_round()     burning, regeneration, lingering spells all tick
    6. back to 2, with your action and bonus refreshed

The two flags that drive all of this are self.player_action_available and
self.player_bonus_available. Both reset at the top of your turn.

HASTE gets special handling: while active you get one extra action per round,
tracked as self.extra_action_available. spend_action() below is what makes
this work - it eats the extra action first, before your real one.

BOSSES are ordinary enemies with a handful of extra keys - boss, attacks,
special, resist, vulnerable - so targeting, damage and holds all work on them
unchanged. What is different lives in two places: boss_special() (their
signature move, on a cooldown) and the enrage check in _enemy_turn_step, which
gives them an extra attack below half health. make_boss builds them from the
BOSSES table in data.py.

RUNNING AWAY
do_flee() is a Dexterity check against a DC set by the floor, how many enemies
there are, and whether one of them is a boss. Win and you retreat to the room
you came from, leaving the enemies where they stand. Lose and they get a free
round at you. Smoke bombs, cloaks and boots all make it easier; Misty Step and
Dimension Door make it certain.

WHERE TO CHANGE THINGS

    Attack damage/accuracy .......... perform_combat_attack, and the three
                                      do_*_attack wrappers that feed it
    Add a new bonus action .......... open_bonus_menu, plus a bonus_* method
    Enemy types, HP, damage ......... make_enemy_pack
    Boss statistics ................. BOSSES in data.py
    Boss signature moves ............ boss_special
    How enemies pick targets ........ _enemy_turn_step
    How hard it is to run ........... flee_dc
    The enemy cards on screen ....... draw_combat / ENEMY_COLORS
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (WEAPONS, FINESSE, RANGED, ARMOR, SHIELDS, MAGIC_ITEMS,
                   CLASSES, DIFFICULTIES, CLASS_SPELLS, BOSSES, BOSS_EVERY,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, SPELL_CATALOG, COMMON_LOOT, DEEP_LOOT,
                   PACK_HP_BUDGET, PACK_HP_PER_FLOOR, BOSS_HP_SCALE,
                   RANGED_ENEMIES, RANGED_VERBS, FEARLESS_ENEMIES, OBSTACLES,
                   OBSTACLE_CHANCE, COVER_AC, PACK_TACTICS_CAP, MORALE_HP_FRAC,
                   MORALE_CHANCE, TELEGRAPHS, KILL_LINES,
                   ADAPTIVE_MIN, ADAPTIVE_MAX, ADAPTIVE_STEP, ADAPTIVE_WINDOW)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class CombatMixin:

    ENEMY_COLORS = {
        'goblin': '#8bc34a', 'giant rat': '#a1887f', 'kobold': '#ffb74d',
        'giant spider': '#9575cd', 'skeleton': '#cfcabc', 'zombie': '#9ccc65',
        'orc': '#7cb342', 'ghost': '#b3e5fc', 'cultist': '#ef9a9a',
        'gnoll': '#d4a373', 'harpy': '#ce93d8', 'animated armor': '#b0bec5',
        'troll': '#558b2f', 'wraith': '#90a4ae', 'ogre': '#a1887f',
        'basilisk': '#8d6e63', 'minotaur': '#a1523f', 'fire elemental': '#ff8a65',
        'hell hound': '#e57373', 'stone golem': '#9e9e9e', 'young wyrm': '#ffab40',
    }

    BOSS_COLOR = '#f0c419'

    # ------------------------------------------------------------- targeting

    def living_enemies(self):
        """Every enemy still standing. Dead ones stay in the list so their card remains visible."""
        return [e for e in self.enemies if e['hp'] > 0]

    def current_target(self):
        """The enemy you are attacking, moving to the first living one if yours has died."""
        living = self.living_enemies()
        if not living:
            return None
        if self.target_index >= len(self.enemies) or self.enemies[self.target_index]['hp'] <= 0:
            self.target_index = self.enemies.index(living[0])
        return self.enemies[self.target_index]

    def set_target(self, idx):
        """Aim at enemy number `idx` - called when you click an enemy card."""
        if 0 <= idx < len(self.enemies) and self.enemies[idx]['hp'] > 0:
            self.target_index = idx
            self.draw_combat()

    def card_x(self, idx):
        """Left edge in pixels of enemy card `idx` on the combat canvas."""
        # the companion marker sits between you and the enemies, so the cards
        # slide right to make room while one is hired
        return 104 + (64 if getattr(self, 'companion', None) else 0) + idx * 182

    def fighting_boss(self):
        """True if any enemy still standing is a boss."""
        return any(e.get('boss') for e in self.living_enemies())

    # ------------------------------------------------------------ the panel

    def show_combat_panel(self):
        """Reveal the enemy display at the start of a fight."""
        if not getattr(self, 'combat_panel_visible', False):
            self.combat_frame.pack(fill=tk.X, pady=(4, 8), before=self.buttons_frame)
            self.combat_panel_visible = True
        self.draw_combat()

    def _maybe_hide_combat_panel(self):
        # delayed hide: skip if a new fight started in the meantime
        """Hide the panel, but only if a new fight has not already started."""
        if not self.in_combat:
            self.hide_combat_panel()

    def hide_combat_panel(self):
        """Take the enemy display off screen."""
        if getattr(self, 'combat_panel_visible', False):
            self.combat_frame.pack_forget()
            self.combat_panel_visible = False

    def draw_combat(self):
        """Redraw every enemy card: name, HP bar, conditions, and the TARGET marker.

        Called after anything that changes an enemy - damage, death, retargeting.
        Bosses get a wider gold-bordered card with their condition line under it.
        
"""
        if not getattr(self, 'combat_panel_visible', False):
            return
        p = self.PAL
        c = self.combat_canvas
        c.delete('all')
        self.current_target()  # normalize target_index before drawing

        # the player marker on the left
        c.create_oval(22, 26, 70, 74, fill=p['gold'], outline='')
        c.create_text(46, 50, text='@', font=("Consolas", 20, "bold"), fill='#1b1712')
        c.create_text(46, 86, text='You', fill=p['text'], font=("Segoe UI", 9, "bold"))
        # action-economy pips: A = action, B = bonus action
        act = getattr(self, 'player_action_available', True)
        bon = getattr(self, 'player_bonus_available', True)
        c.create_oval(16, 98, 30, 112, fill=p['hp_hi'] if act else '#3a3128', outline='')
        c.create_text(23, 105, text='A', fill='#1b1712' if act else p['dim'], font=("Segoe UI", 8, "bold"))
        c.create_oval(62, 98, 76, 112, fill=p['xp'] if bon else '#3a3128', outline='')
        c.create_text(69, 105, text='B', fill='#1b1712' if bon else p['dim'], font=("Segoe UI", 8, "bold"))
        status_bits = []
        if getattr(self, 'temp_hp', 0):
            status_bits.append(f"+{self.temp_hp} temp")
        if getattr(self, 'player_in_cover', False):
            status_bits.append("in cover")
        if status_bits:
            c.create_text(46, 14, text=' \u00b7 '.join(status_bits), fill=p['xp'],
                          font=("Segoe UI", 8, "bold"))

        # the hired companion stands between you and them
        comp = getattr(self, 'companion', None)
        if comp:
            c.create_oval(80, 34, 112, 66, fill='#80cbc4', outline='')
            c.create_text(96, 50, text=comp['name'][0].upper(),
                          font=("Consolas", 13, "bold"), fill='#1b1712')
            c.create_text(96, 78, text=comp['name'], fill=p['text'], font=("Segoe UI", 8, "bold"))
            comp_bits = f"{comp['hp']}/{self.companion_max_hp()}"
            if comp.get('in_cover'):
                comp_bits += " \u00b7 cover"
            c.create_text(96, 92, text=comp_bits, fill=p['dim'], font=("Segoe UI", 8))

        for i, e in enumerate(self.enemies):
            x = self.card_x(i)
            alive = e['hp'] > 0
            boss = e.get('boss')
            c.create_rectangle(x, 8, x + 170, 110,
                               fill='#3a2f16' if (alive and boss) else ('#2e2822' if alive else '#211d18'),
                               outline=(self.BOSS_COLOR if boss else p['accent']) if alive else '#3a3128',
                               width=2 if boss else 1)
            if alive:
                color = self.BOSS_COLOR if boss else self.ENEMY_COLORS.get(e['name'], '#ef9a9a')
            else:
                color = '#5a544a'
            c.create_oval(x + 12, 20, x + 48, 56, fill=color, outline='')
            c.create_text(x + 30, 38, text=e['name'][0].upper(),
                          font=("Consolas", 15, "bold"), fill='#1b1712')
            label = e['name'].title()
            c.create_text(x + 56, 26, text=label, anchor=tk.W,
                          fill=(self.BOSS_COLOR if boss and alive else
                                (p['text'] if alive else p['dim'])),
                          font=("Segoe UI", 10, "bold"))
            bw = 146
            c.create_rectangle(x + 12, 66, x + 12 + bw, 82, fill=p['field'], outline='')
            if alive:
                tags = [f"AC {e['ac']}"]
                if e.get('attacks', 1) > 1:
                    tags.append(f"x{e['attacks']}")
                if e.get('enraged'):
                    tags.append("ENRAGED")
                c.create_text(x + 56, 42, text='  '.join(tags), anchor=tk.W,
                              fill=p['hp_lo'] if e.get('enraged') else p['dim'],
                              font=("Segoe UI", 9))
                conditions = []
                if e.get('dist') == 'far':
                    conditions.append('at range')
                if e.get('in_cover'):
                    conditions.append('cover')
                if e.get('held'):
                    conditions.append('held')
                if e.get('charmed'):
                    conditions.append('charmed')
                if e.get('burning'):
                    conditions.append('burning')
                if conditions:
                    c.create_text(x + 56, 56, text=', '.join(conditions), anchor=tk.W,
                                  fill=p['xp'], font=("Segoe UI", 8, "bold"))
                frac = e['hp'] / e['max_hp']
                col = p['hp_hi'] if frac > 0.5 else (p['hp_mid'] if frac > 0.25 else p['hp_lo'])
                c.create_rectangle(x + 12, 66, x + 12 + int(bw * frac), 82, fill=col, outline='')
                c.create_text(x + 12 + bw // 2, 74, text=f"{e['hp']}/{e['max_hp']}",
                              fill=p['text'], font=("Segoe UI", 8, "bold"))
            else:
                c.create_text(x + 12 + bw // 2, 74,
                              text="fled" if e.get('fled') else "defeated",
                              fill=p['dim'], font=("Segoe UI", 8, "bold"))
            if alive and i == self.target_index:
                c.create_rectangle(x - 2, 6, x + 172, 112, outline=p['gold'], width=2)
                c.create_text(x + 85, 98, text='TARGET', fill=p['gold'], font=("Segoe UI", 8, "bold"))
            tag = f"card{i}"
            c.create_rectangle(x, 8, x + 170, 110, fill='', outline='', tags=(tag,))
            c.tag_bind(tag, '<Button-1>', lambda ev, idx=i: self.set_target(idx))

    # -------------------------------------------------------- dealing damage

    def hit_enemy(self, enemy, amount, kind="", attacker=None):
        """Apply `amount` damage to one enemy, with the flash and floating number.

        Resistances halve the damage and vulnerabilities add half again - which is
        what makes choosing the right spell against a boss matter. Handles the enemy
        dying, so callers do not need to check HP themselves. Pass attacker='Bren'
        when the damage is not the player's own (a companion), so the log reads right.
        
"""
        kind_l = (kind or '').lower()
        note = ''
        if kind_l and kind_l in [r.lower() for r in enemy.get('resist', [])]:
            amount = max(1, amount // 2)
            note = f" (the {enemy['name']} shrugs off much of the {kind_l})"
        elif kind_l and kind_l in [v.lower() for v in enemy.get('vulnerable', [])]:
            amount = amount + amount // 2
            note = f" (the {enemy['name']} recoils from {kind_l}!)"

        enemy['hp'] = max(0, enemy['hp'] - amount)
        idx = self.enemies.index(enemy)
        self.flash_card(idx)
        self.float_text(self.card_x(idx) + 85, 42, f"-{amount}", '#ffcc80')
        who = f"{attacker} deals" if attacker else "You deal"
        if kind:
            self.log_message(f"{who} {amount} {kind} damage to the {enemy['name']}.{note}",
                             color='important' if note else 'black')
        elif note:
            self.log_message(f"{who} {amount} damage to the {enemy['name']}.{note}",
                             color='important')
        # the tide-turning moment reads better when the game notices it
        if (enemy['hp'] > 0 and not enemy.get('boss') and not enemy.get('bloodied')
                and enemy['hp'] <= enemy['max_hp'] // 2):
            enemy['bloodied'] = True
            self.log_message(f"The {enemy['name']} staggers, bloodied.", color='enemy')
        if enemy['hp'] <= 0:
            self.defeat_enemy(enemy)
        else:
            self.draw_combat()

    def damage_player(self, amount, reason, color='warning'):
        """Take damage, honouring temporary HP, damage reduction, and death wards.

        Everything that hurts the player goes through here, in combat and out of it,
        so that a belt of the bulwark and a Death Ward work the same wherever the
        damage came from. Returns the amount that actually landed.
        
"""
        reduction = getattr(self, 'damage_reduction', 0)
        if reduction:
            blocked = min(reduction, amount - 1) if amount > 1 else 0
            amount -= blocked
            if blocked:
                reason += f" ({blocked} turned aside by your gear)"

        temp = getattr(self, 'temp_hp', 0)
        if temp:
            soaked = min(temp, amount)
            self.temp_hp = temp - soaked
            amount -= soaked
            self.log_message(f"{reason} {soaked} of it is soaked by your temporary HP"
                             + (f", leaving {self.temp_hp}." if self.temp_hp else " - which is now gone."),
                             color=color)
            if amount <= 0:
                self.refresh_stats()
                return 0
            reason = "The rest gets through:"

        self.health -= amount
        self.log_message(f"{reason} You take {amount} damage.", color=color)

        if self.health <= 0 and getattr(self, 'death_ward', False):
            self.death_ward = False
            self.health = 1
            self.play_sound('levelup')
            self.log_message("Your ward flares white and catches you at 1 HP. It is spent.",
                             color='important')
        # the narrator: in a fight, damage is pooled and spoken once per round
        # (start_of_round); outside one, a trap or poison speaks right away
        if amount > 0:
            if getattr(self, 'in_combat', False):
                self._narr_dmg_round = getattr(self, '_narr_dmg_round', 0) + amount
            else:
                self.narrate(f"You take {amount} damage. "
                             f"{max(0, self.health)} health left.")
        self.refresh_stats()
        return amount

    # --------------------------------------------------------- the enemy turn

    def resolve_enemy_attack(self):
        """Begin the enemies' turn by queueing up everyone still alive."""
        if not self.in_combat or not self.enemy_attack_pending:
            return
        self.enemy_attack_pending = False
        self._enemy_queue = list(self.living_enemies())
        self._enemy_turn_step()

    def _enemy_turn_step(self):
        """Resolve one enemy's attacks, then schedule the next a moment later.

        Enemies attack one at a time on a timer rather than all at once, so the log
        stays readable. Bosses take their signature move first when it is off
        cooldown, then swing as many times as their statblock says. When the queue
        empties the round is over: start_of_round handles everything that ticks.
        
"""
        if not self.in_combat:
            return
        if not self._enemy_queue:
            self.start_of_round()
            return
        e = self._enemy_queue.pop(0)
        if e['hp'] > 0:
            if e.get('dominated'):
                e['dominated'] -= 1
                allies = [o for o in self.living_enemies() if o is not e]
                if allies:
                    victim = random.choice(allies)
                    dmg = random.randint(1, e['dmg']) + random.randint(1, e['dmg'])
                    self.log_message(f"Under your command, the {e['name']} turns on the "
                                     f"{victim['name']}!", color='important')
                    self.hit_enemy(victim, dmg, 'domination')
                else:
                    self.log_message(f"The {e['name']} stands helplessly at your side.",
                                     color='important')
                if not e['dominated']:
                    self.log_message(f"The {e['name']} blinks and remembers whose side it is on.")
                self.draw_combat()
            elif e.get('charmed'):
                e['charmed'] = False
                self.log_message(f"The {e['name']} lowers its weapon, still under your spell.",
                                 color='important')
                self.draw_combat()
            elif e.get('held'):
                e['held'] = False
                self.log_message(f"The {e['name']} is held motionless and cannot attack!", color="important")
                self.draw_combat()
            elif e.get('boss'):
                # a boss below half health fights harder from here on
                if not e.get('enraged') and e['hp'] <= e['max_hp'] // 2:
                    e['enraged'] = True
                    e['atk'] += 2
                    e['attacks'] = e.get('attacks', 1) + 1
                    self.play_sound('enemy_hit')
                    self.log_message(f"The {e['name']} is wounded and furious! It fights harder now.",
                                     color='enemy')
                    self.draw_combat()
                # signature move first, if it is ready
                if e.get('cooldown', 0) <= 0:
                    e['cooldown'] = e.get('cooldown_max', 3)
                    if self.boss_special(e):
                        # the special replaced this turn's attacks
                        if self.health <= 0:
                            return
                        self.root.after(500, self._enemy_turn_step)
                        return
                else:
                    e['cooldown'] = e.get('cooldown', 0) - 1
                    # TELEGRAPH: one round's warning before the big move, so
                    # Taking Cover or Falling Back in time is a real decision
                    if e['cooldown'] <= 0:
                        tel = TELEGRAPHS.get(e.get('special'))
                        if tel:
                            self.log_message(tel.format(name=e['name']), color='enemy')
                            if (e.get('special') in ('breath', 'quake')
                                    and getattr(self, 'obstacle', None)):
                                self.narrate("Big attack coming. Take cover!")
                            else:
                                self.narrate("Watch out. Big attack coming.")
                for _ in range(max(1, e.get('attacks', 1))):
                    if self.health <= 0 or not self.in_combat:
                        return
                    if not self.enemy_single_attack(e):
                        return
            else:
                # ordinary enemies think for themselves now: morale, kiting,
                # rushing in, pack tactics - all in enemy_take_turn below
                if not self.enemy_take_turn(e):
                    return
        # Enemies attack one at a time on a timer instead of all at once, so the
        # log stays readable. 450ms is the gap between them.
        self.root.after(450, self._enemy_turn_step)

    def enemy_single_attack(self, e, atk_bonus=0):
        """One swing (or shot) from one enemy. Returns False if the player has died.

        atk_bonus carries pack tactics (+1 per other near ally, capped). Your
        companion may step in and take the hit instead; cover adds to your AC
        against ranged attackers only - anything already in your face just
        walks around the barricade.
        """
        if getattr(self, 'wall_of_force', False):
            self.log_message(f"The {e['name']} batters uselessly at your wall of force.",
                             color='important')
            return True
        # a hired ally draws some of what was meant for you
        if self.companion_should_intercept(e):
            return self.companion_absorb_attack(e)
        is_shot = e.get('ranged') and e.get('dist') == 'far'
        roll = random.randint(1, 20)
        total = roll + e['atk'] + atk_bonus + self.enemy_attack_penalty
        ac = self.player_ac
        covered = getattr(self, 'player_in_cover', False) and is_shot
        if covered:
            ac += COVER_AC
        if total >= ac:
            self.play_sound('enemy_hit')
            dmg = random.randint(1, e['dmg'])
            # Bosses no longer roll a hidden second die on top of multiattack:
            # that was rocket-tag against a D&D-sized HP pool. Their threat is
            # all in the open now - attacks x dmg from BOSSES in data.py, the
            # signature move, and the enrage below half health - which also
            # means Size Up the Enemy tells the truth about what they hit for.
            verb = RANGED_VERBS.get(e['name'], 'picks you off from range') if is_shot else 'hits you'
            landed = self.damage_player(
                dmg, f"The {e['name']} {verb}. ({roll} +{e['atk'] + atk_bonus} = {total})")
            if landed:
                self.float_text(46, 38, f"-{landed}", self.PAL['hp_lo'])
            if getattr(self, 'frost_armor', False) and self.temp_hp:
                cold = random.randint(1, 6) + 4
                self.log_message(f"Ice flares where it struck you \u2014 the {e['name']} "
                                 f"takes {cold} cold damage.", color='important')
                self.hit_enemy(e, cold, 'cold')
                if e['hp'] <= 0:
                    return True
            elif getattr(self, 'frost_armor', False) and not self.temp_hp:
                self.frost_armor = False
                self.log_message("The last of your frost armor cracks away.")
            if e.get('drains') and landed:
                healed = min(e['max_hp'] - e['hp'], landed // 2)
                if healed:
                    e['hp'] += healed
                    self.log_message(f"The {e['name']} drinks your strength and recovers {healed} HP.",
                                     color='enemy')
                    self.draw_combat()
            if self.health <= 0:
                self.hide_combat_panel()
                self.handle_death()
                return False
        else:
            if covered and total >= self.player_ac:
                spot = self.obstacle[0] if getattr(self, 'obstacle', None) else 'your cover'
                self.log_message(f"The {e['name']}'s shot thuds into {spot}. "
                                 f"({roll} +{e['atk'] + atk_bonus} = {total})", color="enemy")
            else:
                self.log_message(f"The {e['name']} misses you. ({roll} +{e['atk'] + atk_bonus} "
                                 f"= {total})", color="enemy")
        return True

    def enemy_take_turn(self, e):
        """One ordinary enemy's whole turn: morale, movement, cover, then attacks.

        This is the tactical brain for everything that is not a boss. It is a
        short priority list, deliberately readable top to bottom:

            1. MORALE   - a badly hurt survivor of a broken pack may bolt.
                          The mindless (FEARLESS_ENEMIES) never do.
            2. KITE     - a hurt skirmisher you have closed with opens the
                          distance again (once), ducking into cover if the room
                          has any. Repositioning costs it its attacks.
            3. RUSH     - a melee straggler still at range closes in, and
                          still gets to swing: closing is free for them too.
            4. PACK     - each other near melee ally emboldens it: +1 to hit,
                          capped at PACK_TACTICS_CAP. Falling Back strips it.

        Returns False if the player died mid-turn, so the caller stops the queue.
        """
        # 1. morale
        if (not e.get('fearless')
                and e['hp'] <= e['max_hp'] * MORALE_HP_FRAC
                and len(self.living_enemies()) * 2 <= max(1, getattr(self, '_pack_start_count', 1))
                and random.random() < MORALE_CHANCE):
            self.enemy_flees(e)
            return True

        # 2. kite: hurt skirmishers open the distance again
        if (e.get('ranged') and e.get('dist') == 'near'
                and e.get('retreats_left', 0) > 0 and e['hp'] < e['max_hp'] * 0.5):
            e['retreats_left'] -= 1
            e['dist'] = 'far'
            if getattr(self, 'obstacle', None) and not e.get('in_cover'):
                e['in_cover'] = True
                self.log_message(f"The {e['name']} scrambles back behind {self.obstacle[0]}.",
                                 color='enemy')
            else:
                self.log_message(f"The {e['name']} falls back out of your reach.", color='enemy')
            self.draw_combat()
            return True  # repositioning costs its attacks

        # 3. rush: melee stragglers close in, then still swing
        if not e.get('ranged') and e.get('dist') == 'far':
            e['dist'] = 'near'
            self.log_message(f"The {e['name']} rushes in!", color='enemy')
            self.draw_combat()

        # 4. pack tactics
        atk_bonus = 0
        if e.get('dist') == 'near' and not e.get('ranged'):
            others = [o for o in self.living_enemies()
                      if o is not e and o.get('dist') == 'near'
                      and not o.get('ranged') and not o.get('boss')]
            atk_bonus = min(PACK_TACTICS_CAP, len(others))
            if atk_bonus and not getattr(self, '_pack_tactics_on', False):
                self._pack_tactics_on = True
                self.log_message("They press in together, covering each other's openings "
                                 "(+1 to hit while they gang up).", color='enemy')

        for _ in range(max(1, e.get('attacks', 1))):
            if self.health <= 0 or not self.in_combat:
                return self.health > 0
            if not self.enemy_single_attack(e, atk_bonus=atk_bonus):
                return False
        return True

    def enemy_flees(self, e):
        """A morale break: the enemy bolts. Small XP (you broke it), no loot."""
        self.play_sound('door')
        self.log_message(f"The {e['name']} takes one look at how this is going, loses its "
                         "nerve, and bolts into the dark!", color='important')
        self.narrate(f"The {e['name']} runs away!")
        e['fled'] = True
        diff = DIFFICULTIES.get(getattr(self, 'difficulty', 'Normal'), DIFFICULTIES['Normal'])
        xp_gain = max(1, int((6 + (self.current_floor() - 1) * 2) * diff['xp']))
        self.add_xp(xp_gain)
        self.defeat_enemy(e, reward=False)

    def boss_special(self, boss):
        """A boss's signature move. Returns True if it used up the boss's whole turn.

        Add a move by adding a key to BOSSES in data.py and a branch here. Anything
        not handled below simply falls through and the boss attacks normally.
        
"""
        move = boss.get('special')

        if move == 'rally':
            allies = [e for e in self.living_enemies() if e is not boss]
            if allies:
                for a in allies:
                    healed = min(a['max_hp'] - a['hp'], 8)
                    a['hp'] += healed
                    a['atk'] += 1
                self.log_message(f"The {boss['name']} roars an order: its followers rally, "
                                 "healed and emboldened!", color='enemy')
            else:
                minion = self.make_enemy_pack(self.current_floor(), count=1)[0]
                minion['name'] = 'goblin'
                self.enemies.append(minion)
                self.log_message(f"The {boss['name']} bellows and another goblin scrambles "
                                 "out of the dark!", color='enemy')
            self.play_sound('enemy_hit')
            self.draw_combat()
            return True

        if move == 'drain':
            # 2d8, not 3d8: the gravebound is a floor-3-to-6 boss, and its old
            # drain took nearly half a level-2 character's pool in one move
            dmg = sum(random.randint(1, 8) for _ in range(2))
            self.play_sound('spell')
            landed = self.damage_player(dmg, f"The {boss['name']} raises a hand and your "
                                             "warmth pours out of you.")
            healed = min(boss['max_hp'] - boss['hp'], landed)
            boss['hp'] += healed
            if healed:
                self.log_message(f"The {boss['name']} recovers {healed} HP.", color='enemy')
            self.draw_combat()
            if self.health <= 0:
                self.hide_combat_panel()
                self.handle_death()
            return True

        if move == 'web':
            self.entangled = 2
            self.play_sound('trap_spring')
            self.log_message(f"The {boss['name']} sprays webbing across you - you are stuck fast "
                             "and will lose your bonus action for two rounds.", color='enemy')
            return True

        if move == 'curse':
            self.cursed_rounds = 3
            self.play_sound('spell')
            self.log_message(f"The {boss['name']} speaks your name backwards. A curse settles: "
                             "-3 to your attacks for three rounds.", color='enemy')
            return True

        if move == 'quake':
            dmg = sum(random.randint(1, 6) for _ in range(4))
            self.play_sound('crit')
            self.entangled = 1
            if getattr(self, 'player_in_cover', False):
                dmg //= 2
                spot = self.obstacle[0] if getattr(self, 'obstacle', None) else 'your cover'
                self.log_message(f"You brace behind {spot} - only half the shock reaches you.",
                                 color='important')
                self._maybe_smash_obstacle()
            self.damage_player(dmg, f"The {boss['name']} brings both fists down and the floor "
                                    "bucks under you.")
            if self.health <= 0:
                self.hide_combat_panel()
                self.handle_death()
            return True

        if move == 'breath':
            dmg = sum(random.randint(1, 6) for _ in range(6))
            self.play_sound('crit')
            if getattr(self, 'player_in_cover', False):
                dmg //= 2
                spot = self.obstacle[0] if getattr(self, 'obstacle', None) else 'your cover'
                self.log_message(f"You flatten yourself behind {spot} as the fire washes over "
                                 "- half of it finds you.", color='important')
                self._maybe_smash_obstacle()
            self.damage_player(dmg, f"The {boss['name']} inhales, and the room turns to fire.")
            if self.health <= 0:
                self.hide_combat_panel()
                self.handle_death()
            return True

        return False

    def _maybe_smash_obstacle(self):
        """A boss's big move sometimes destroys the cover that just blunted it."""
        if getattr(self, 'obstacle', None) and random.random() < 0.4:
            self.log_message(f"...and {self.obstacle[0]} is blasted apart! No more cover here.",
                             color='warning')
            self.obstacle = None
            self.player_in_cover = False
            if getattr(self, 'companion', None):
                self.companion['in_cover'] = False
            for e in self.enemies:
                e['in_cover'] = False
            self.draw_combat()

    def current_floor(self):
        """Which dungeon floor you are on, or 1 if you are not in the dungeon."""
        return self.dungeon.get('floor', 1) if getattr(self, 'dungeon', None) else 1

    def start_of_round(self):
        """Everything that ticks at the top of your turn: burns, regeneration, buffs.

        Called once the enemy queue empties. This is where lingering effects on both
        sides resolve, and where your action and bonus action come back.
        
"""
        self.enemy_attack_penalty = 0
        if getattr(self, 'defend_active', False):
            self.defend_active = False
            self.update_derived_stats()
            self.log_message("You relax your guard.")
        if getattr(self, 'wall_of_force', False):
            self.wall_of_force = False
            self.log_message("Your wall of force winks out.")

        # fires you started keep burning
        for key, entry in list(getattr(self, 'burning_enemies', {}).items()):
            enemy, rounds = entry
            if enemy['hp'] <= 0 or rounds <= 0:
                enemy['burning'] = 0
                self.burning_enemies.pop(key, None)
                continue
            entry[1] -= 1
            enemy['burning'] = entry[1]
            burn = random.randint(1, 6)
            self.log_message(f"The {enemy['name']} is still burning ({burn} fire damage).",
                             color='important')
            self.hit_enemy(enemy, burn, 'fire')

        # a spiritual weapon keeps swinging at your target on its own
        if getattr(self, 'spirit_weapon', 0) and self.living_enemies():
            t = self.current_target()
            dmg = sum(random.randint(1, 8) for _ in range(self.spirit_weapon))
            self.log_message("Your spiritual weapon darts in on its own.", color='important')
            if t:
                self.hit_enemy(t, dmg, 'force')

        # area spells that were left running: storms, walls, guardians, swarms
        for effect in list(getattr(self, 'lingering', []) or []):
            if not self.living_enemies():
                break
            effect['rounds'] -= 1
            dmg = sum(random.randint(1, effect['sides']) for _ in range(effect['count']))
            self.log_message(f"{effect['label']} ({dmg} {effect['kind']}).", color='important')
            for en in list(self.living_enemies()):
                self.hit_enemy(en, dmg, effect['kind'])
            if effect['rounds'] <= 0:
                try:
                    self.lingering.remove(effect)
                except ValueError:
                    pass

        # regeneration from a ring or a crown
        regen = self.gear_effects().get('regen', 0)
        if regen and self.health < self.max_health:
            healed = min(self.max_health - self.health, regen)
            self.health += healed
            self.log_message(f"Your gear knits the damage closed (+{healed} HP).")

        # conditions on you wear off
        if getattr(self, 'cursed_rounds', 0):
            self.cursed_rounds -= 1
            if not self.cursed_rounds:
                self.log_message("The curse on you lifts.", color='important')
        if getattr(self, 'poisoned', 0):
            self.poisoned -= 1
            self.damage_player(random.randint(1, 4), "The poison in your blood burns.")
            if self.health <= 0:
                self.hide_combat_panel()
                self.handle_death()
                return
            if not self.poisoned:
                self.log_message("The poison finally works its way out.", color='important')

        self.player_action_available = True
        self.player_bonus_available = True
        self.player_move_available = True
        self._fight_round_count = getattr(self, '_fight_round_count', 0) + 1
        # the narrator's one line per round: what that cost you, all together
        taken = getattr(self, '_narr_dmg_round', 0)
        if taken:
            self._narr_dmg_round = 0
            if self.health <= self.max_health * 0.3:
                self.narrate(f"Careful! You took {taken} damage. "
                             f"Only {self.health} health left.")
            else:
                self.narrate(f"You took {taken} damage. {self.health} health left.")
        if getattr(self, 'entangled', 0):
            self.entangled -= 1
            self.player_bonus_available = False
            self.log_message("You are still stuck fast - no bonus action this round.", color='warning')
        self.smoke_cover = False
        self.tick_haste()
        if not self.living_enemies():
            return
        self.log_message("Your turn. Choose your next attack.", color="important")
        self.refresh_stats()
        self.refresh_buttons()

    # ------------------------------------------------------ starting a fight

    def do_attack(self):
        """Begin combat with whatever the dungeon just put in front of you.

        Resets per-fight resources (sneak attack, second wind) and clears any buff
        left over from the last fight, so nothing carries between encounters.
        
"""
        if self.in_combat:
            self.log_message("You are already in combat. Choose an attack option.")
            return

        if self.current_event == "shop":
            self.log_message("You are in a shop. Attack is not available here.", color="warning")
            return

        # 'boss' is accepted as well as 'enemy' so that a boss room can hand off
        # here directly without every caller having to remember to relabel itself
        if self.current_event not in ("enemy", "boss") or not self.pending_enemies:
            self.log_message("There is nothing hostile to attack right now. Explore until you find an enemy.")
            return

        self.enemies = self.pending_enemies
        self.pending_enemies = []
        self.target_index = 0
        self.current_event = None
        self.combat_round = 0
        self.in_combat = True
        # initialize per-combat class resources
        if self.char_class == "Rogue":
            self.sneak_available = True
            self.sneak_active = False
        elif self.char_class == "Fighter":
            self.second_wind_available = True
            self.action_surge_available = True
        # per-round player action economy
        self.player_action_available = True
        self.player_bonus_available = True
        # buffs never carry over from a previous fight
        self.end_haste(silent=True)
        self.clear_combat_effects()
        self.enemy_attack_penalty = 0
        # positioning: ranged enemies open the fight hanging back; the rest
        # are already in your face. Rooms sometimes offer something to duck
        # behind (Move -> Take Cover). All per-fight, wiped by clear_combat_effects.
        for e in self.enemies:
            e.setdefault('ranged', e.get('name') in RANGED_ENEMIES)
            e.setdefault('dist', 'far' if e.get('ranged') else 'near')
            e.setdefault('in_cover', False)
            e.setdefault('retreats_left', 1)
            e.setdefault('fearless', bool(e.get('boss')) or e.get('name') in FEARLESS_ENEMIES)
        self.obstacle = random.choice(OBSTACLES) if random.random() < OBSTACLE_CHANCE else None
        self.player_move_available = True
        self.player_in_cover = False
        if getattr(self, 'companion', None):
            self.companion['in_cover'] = False
        # what the adaptive dial and morale read later
        self._pack_start_count = len(self.enemies)
        self._pack_tactics_on = False
        self._fight_hp_start = self.health
        self._fight_round_count = 0
        initiative_roll = random.randint(1, 20)
        self.log_message(f"You roll initiative: {initiative_roll}.", color="important")
        boss = next((e for e in self.enemies if e.get('boss')), None)
        if boss:
            self.play_sound('death')
            self.log_message(boss.get('title', 'Something enormous blocks your way.'), color='enemy')
            self.log_message(f"BOSS: {boss['name'].title()} \u2014 {boss['max_hp']} HP, AC {boss['ac']}, "
                             f"{boss.get('attacks', 1)} attacks a round.", color='enemy')
            if boss.get('resist'):
                self.log_message(f"It takes half damage from: {', '.join(boss['resist'])}.", color='warning')
            if boss.get('vulnerable'):
                self.log_message(f"It looks badly hurt by: {', '.join(boss['vulnerable'])}.", color='important')
        desc = ', '.join(f"{e['name']} ({e['hp']} HP)" for e in self.enemies)
        self.log_message(f"You engage: {desc}.", color="important")
        far = [e['name'] for e in self.enemies if e.get('dist') == 'far']
        if far:
            self.log_message(f"Hanging back out of reach: {', '.join(far)}. Melee swings will "
                             "close the distance on their own; ranged weapons and spells reach "
                             "them where they stand.", color='warning')
        if self.obstacle:
            self.log_message(self.obstacle[1] + " (Move \u2192 Take Cover to use it.)",
                             color='important')
        if len(self.enemies) > 1:
            self.log_message("Click an enemy card to choose your target. Area spells hit them all!", color="important")
        self.log_message("If it is going badly, Flee is always on the table.", color='important')
        self.show_combat_panel()
        self.refresh_stats()
        self.refresh_buttons()

    # -------------------------------------------------------- running away

    def flee_dc(self):
        """How hard it is to get out of this fight right now."""
        enemies = self.living_enemies()
        dc = 9 + self.current_floor() + 2 * max(0, len(enemies) - 1)
        if self.fighting_boss():
            dc += 5
        return dc

    def do_flee(self):
        """Try to run. A Dexterity check against flee_dc; failure costs you the round.

        Success retreats you to the room you came from and leaves the enemies where
        they stand, so the fight is still there if you come back with more potions.
        Misty Step and Dimension Door skip the roll entirely.
        
"""
        if not self.in_combat:
            self.log_message("There is nothing to run from.")
            return
        if getattr(self, 'enemy_attack_pending', False):
            self.log_message("The enemies are already mid-swing.")
            return

        dc = self.flee_dc()
        if getattr(self, 'escape_ready', False):
            self.escape_ready = False
            self.log_message("You step sideways through space and simply are not there any more.",
                             color='important')
            self.escape_combat()
            return

        bonus = self.ability_mod('dexterity')
        bonus += self.gear_effects().get('flee_bonus', 0)
        bonus += DIFFICULTIES.get(getattr(self, 'difficulty', 'Normal'),
                                  DIFFICULTIES['Normal']).get('flee', 0)
        if getattr(self, 'smoke_cover', False):
            bonus += 6
        if getattr(self, 'haste_active', False):
            bonus += 4
        living = self.living_enemies()
        if living and all(e.get('dist') == 'far' for e in living):
            bonus += 3
            self.log_message("Nothing is within arm's reach of you - a head start (+3).",
                             color='player')
        roll = random.randint(1, 20)
        self.show_dice_roll(roll)
        total = roll + bonus
        self.log_message(f"You break for the door: {roll} {bonus:+d} = {total} vs DC {dc}.",
                         color='player')

        if roll == 20 or total >= dc:
            self.play_sound('door')
            self.log_message("You get clear! No loot, no experience - but you are alive.",
                             color='important')
            self.escape_combat()
            return

        self.play_sound('fail')
        self.log_message("You do not get far enough, and they are between you and the door.",
                         color='warning')
        self.player_action_available = False
        self.player_bonus_available = False
        self.enemy_attack_pending = True
        self.refresh_buttons()
        self.resolve_enemy_attack()

    def escape_combat(self):
        """Leave a fight without winning it: the enemies stay put and you back out."""
        fled = list(self.living_enemies())
        self.in_combat = False
        self.enemy_attack_pending = False
        self.enemies = []
        self.end_haste(silent=True)
        self.clear_combat_effects()
        # put the enemies back in the room so the fight is there if you return
        d = getattr(self, 'dungeon', None)
        if d and fled:
            room = d['rooms'].get(d['pos'])
            if room is not None:
                room['type'] = self._fled_room_type if getattr(self, '_fled_room_type', None) else 'enemy'
            back = getattr(self, '_last_pos', None)
            if back and back in d['rooms']:
                d['pos'] = back
                self.log_message("You fall back to the room you came from.", color='important')
            self.draw_dungeon()
        self.current_event = None
        self.pending_enemies = []
        self.refresh_stats()
        self.refresh_inventory()
        self.refresh_buttons()
        self.root.after(1000, self._maybe_hide_combat_panel)

    # ---------------------------------------------------------------- rewards

    def defeat_enemy(self, enemy, reward=True):
        """Handle one enemy going down: gold, XP, a possible item drop.

        Ends the fight if it was the last one standing. Pass reward=False for kills
        that should not pay out, such as enemies removed by Sleep. Bosses pay out on
        a different scale and always leave a magic item behind.
        
"""
        floor = self.current_floor()
        enemy['hp'] = 0
        if reward:
            diff = DIFFICULTIES.get(getattr(self, 'difficulty', 'Normal'), DIFFICULTIES['Normal'])
            if enemy.get('boss'):
                gold_gain = int((random.randint(60, 110) + floor * 20) * diff['gold'])
                xp_gain = int((random.randint(120, 180) + floor * 40) * diff['xp'])
                self.gold += gold_gain
                self.add_xp(xp_gain)
                self.play_sound('levelup')
                self.log_message(f"THE {enemy['name'].upper()} FALLS! +{gold_gain} gold, +{xp_gain} XP.",
                                 color='important')
                prize = self.roll_loot(floor, rarity=enemy.get('loot', 'Rare'))
                self.inventory.append(prize)
                self.log_message(f"Among its hoard you find: {prize}.", color='important')
                extra = self.roll_loot(floor, deep=True)
                self.inventory.append(extra)
                self.log_message(f"And tucked beside it, a {extra}.", color='important')
            else:
                gold_gain = int((random.randint(4, 9) + (floor - 1) * 2) * diff['gold'])
                # a touch more base XP than before, so level 3 (second-level
                # slots, one more Hit Die) arrives before the first boss does
                xp_gain = int((random.randint(12, 20) + (floor - 1) * 4) * diff['xp'])
                self.gold += gold_gain
                self.add_xp(xp_gain)
                line = random.choice(KILL_LINES).format(name=enemy['name'])
                msg = f"{line} +{gold_gain} gold, +{xp_gain} XP."
                # struggling players find the dungeon a little more generous
                drop_chance = 0.45
                if getattr(self, 'adaptive_enabled', True):
                    drop_chance += max(0.0, 1.0 - getattr(self, 'adaptive_mult', 1.0))
                if random.random() < drop_chance:
                    item = self.roll_loot(floor, magic_chance=0.05)
                    self.inventory.append(item)
                    msg += f" It dropped a {item}."
                self.log_message(msg, color="important")

        if not self.living_enemies():
            self.play_sound('victory')
            self.log_message("Victory! The room falls silent.", color="important")
            self.narrate("Victory!")
            self.in_combat = False
            self.enemy_attack_pending = False
            # tell the adaptive dial how that went before anything resets
            try:
                self.record_fight_result(died=False)
            except Exception:
                pass
            self.end_haste(silent=True)
            self.clear_combat_effects()
            self.update_derived_stats()
            # a cleared boss room turns into the stairs down (dungeon.py)
            self.on_combat_victory()
            # restore the out-of-combat UI right away, hide the panel shortly after
            self.refresh_stats()
            self.refresh_inventory()
            self.refresh_buttons()
            # clear residual encounter state shortly after victory so exploring
            # and other out-of-combat actions work (gives a short delay so the
            # "defeated" cards remain visible briefly).
            self.root.after(1200, self._maybe_hide_combat_panel)
            try:
                self.root.after(1400, self._clear_post_victory)
            except Exception:
                # fallback for very old tkinter roots or testing environments
                self._clear_post_victory()
        else:
            if not enemy.get('fled'):
                self.narrate(f"{enemy['name']} down.")
            self.current_target()  # retarget onto a living enemy
        self.draw_combat()

    def _clear_post_victory(self):
        """Clear enemy and encounter state after a short delay post-victory."""
        try:
            self.enemies = []
            self.pending_enemies = []
            self.current_event = None
            # ensure combat flags are fully reset
            self.in_combat = False
            self.enemy_attack_pending = False
            self.clear_combat_effects()
            self.refresh_stats()
            self.refresh_inventory()
            self.refresh_buttons()
            # redraw dungeon in case a boss room became stairs
            try:
                self.draw_dungeon()
            except Exception:
                pass
            # finally hide the combat panel if it stuck around
            try:
                self._maybe_hide_combat_panel()
            except Exception:
                pass
        except Exception:
            pass

    # --------------------------------------------------------- your attacks

    def perform_combat_attack(self, name, attack_bonus_mod, damage_dice_count):
        """Roll one attack against the current target and apply the damage.

        The three attack buttons all come through here with different numbers:

            attack_bonus_mod    added to the roll to hit (+2 accurate, -2 wild)
            damage_dice_count   how many weapon dice to roll

        Every rider in the game (sneak attack, rage, hunter's mark, hex, smite,
        magic weapon damage, coated poison) is applied here.

        Spends your ACTION only - it does not end your turn.
        
"""
        if not self.in_combat:
            self.log_message("You are not in combat right now.")
            return

        if self.enemy_attack_pending:
            self.log_message("The enemies are still taking their turn.")
            return
        target = self.current_target()
        if target is None:
            return

        # ensure the player has an action available this round
        if not getattr(self, 'player_action_available', True):
            self.log_message("You have no action available this round.")
            return
        # RANGE: a melee weapon only reaches a near target - but rather than
        # refuse, attacking a far one just closes the distance first, spending
        # your free move for the round. With the move already gone you can
        # still lunge, badly (-4). Ranged weapons skip all of this.
        weapon = getattr(self, 'equipped_weapon', None) or 'unarmed strikes'
        overextended = False
        if target.get('dist') == 'far' and weapon not in RANGED:
            if getattr(self, 'player_move_available', True):
                self.player_move_available = False
                target['dist'] = 'near'
                if getattr(self, 'player_in_cover', False):
                    self.player_in_cover = False
                    self.log_message(f"You break from cover and close on the {target['name']}.",
                                     color='player')
                else:
                    self.log_message(f"You close the distance to the {target['name']}.",
                                     color='player')
                self.draw_combat()
            else:
                overextended = True
        elif weapon not in RANGED and getattr(self, 'player_in_cover', False):
            # swinging a sword means stepping out from behind the barricade
            self.player_in_cover = False
            self.log_message("You step out of cover to swing.", color='player')
            self.draw_combat()
        gear = self.gear_effects()
        self.combat_round += 1
        player_roll = random.randint(1, 20)
        self.show_dice_roll(player_roll)
        attack_modifier = self.player_attack_bonus + attack_bonus_mod
        if self.torch_active:
            attack_modifier += 1
            self.torch_active = False
            self.log_message("Torch flare grants +1 attack bonus.", color="important")
        if self.lantern_active:
            attack_modifier += 1
            self.lantern_active = False
            self.log_message("Lantern glare grants +1 attack bonus.", color="important")
        if getattr(self, 'true_strike_bonus', 0):
            attack_modifier += self.true_strike_bonus
            self.log_message(f"True Strike guides your hand (+{self.true_strike_bonus}).", color="important")
            self.true_strike_bonus = 0
        if getattr(self, 'lucky_bonus', 0):
            attack_modifier += self.lucky_bonus
            self.log_message(f"Your lucky coin pays out (+{self.lucky_bonus}).", color="important")
            self.lucky_bonus = 0
        if getattr(self, 'cursed_rounds', 0):
            attack_modifier -= 3
            self.log_message("The curse drags at your arm (-3).", color="warning")
        if overextended:
            attack_modifier -= 4
            self.log_message(f"The {target['name']} is out of reach and your footing is spent "
                             "- you lunge anyway (-4).", color='warning')
        attack_total = player_roll + attack_modifier
        self.log_message(
            f"{name}: attack roll {player_roll} + {attack_modifier} = {attack_total}.",
            color="player",
        )

        # cover only matters for shots: a far target behind the obstacle is
        # harder to hit with a bow, while melee (which just closed in) and
        # spells (which arc right over it) ignore the barricade entirely
        target_ac = target['ac']
        behind_cover = (target.get('in_cover') and target.get('dist') == 'far'
                        and weapon in RANGED)
        if behind_cover:
            target_ac += COVER_AC

        # A natural 20 always hits regardless of AC (or a 19 with a sword of
        # sharpness), and doubles the damage dice below. Otherwise you need to
        # meet or beat the enemy's Armour Class.
        crit_on = gear.get('crit_range', 20)
        is_crit = player_roll >= crit_on
        if is_crit or attack_total >= target_ac:
            # Weapon work sharpens at levels 5 and 11: every attack rolls an
            # extra die (the martial mirror of cantrips gaining dice at the
            # same levels). Without this, weapon damage was flat from level 1
            # while enemy and boss HP kept growing, and deep fights turned
            # into fifteen-round slogs.
            extra_dice = (1 if self.player_level >= 5 else 0) + (1 if self.player_level >= 11 else 0)
            dice_count = damage_dice_count + extra_dice
            # roll damage dice (double the dice on a critical hit)
            damage_rolls = [random.randint(1, self.player_damage_dice) for _ in range(dice_count)]
            if is_crit:
                damage_rolls += [random.randint(1, self.player_damage_dice) for _ in range(dice_count)]
            damage = sum(damage_rolls) + self.player_damage_bonus
            riders = []
            # magic weapon damage riders, straight from MAGIC_ITEMS
            for (count, die), dtype in gear.get('bonus_damage', []):
                extra = sum(random.randint(1, die) for _ in range(count))
                damage += extra
                riders.append(f"+{extra} {dtype}")
            if getattr(self, 'poison_weapon', 0):
                extra = random.randint(1, 6)
                damage += extra
                riders.append(f"+{extra} poison")
            if getattr(self, 'radiant_weapon', 0):
                extra = random.randint(1, 6)
                damage += extra
                riders.append(f"+{extra} radiant")
            # Rogue sneak attack extra damage (applies on crits too)
            if getattr(self, 'char_class', None) == 'Rogue' and self.sneak_active:
                sneak_extra = sum(random.randint(1, 6)
                                  for _ in range(max(1, (self.player_level + 1) // 2)))
                damage += sneak_extra
                self.sneak_active = False
                self.log_message(f"Sneak Attack deals extra {sneak_extra} damage!", color="important")
            if getattr(self, 'rage_active', False):
                damage += 2
            if getattr(self, 'hunters_mark', False):
                extra = random.randint(1, 6)
                damage += extra
                self.log_message(f"Hunter's Mark adds {extra} damage.", color="important")
            if getattr(self, 'hex_active', False) or getattr(self, 'hex_spell_active', False):
                extra = random.randint(1, 6) if getattr(self, 'hex_spell_active', False) else random.randint(1, 4)
                damage += extra
                self.log_message(f"Your hex adds {extra} damage.", color="important")
            if getattr(self, 'smite_charge', 0):
                smite = sum(random.randint(1, 8) for _ in range(self.smite_charge))
                damage += smite
                self.smite_charge = 0
                self.log_message(f"DIVINE SMITE! +{smite} radiant damage!", color="important")
            if riders:
                self.log_message("Your weapon bites deeper: " + ', '.join(riders) + ".",
                                 color='important')
            self.play_sound('crit' if is_crit else 'hit')
            prefix = f"Critical {name.lower()}!" if is_crit else f"{name}:"
            self.log_message(
                f"{prefix} rolls {damage_rolls} + bonus {self.player_damage_bonus} = {damage}. "
                f"The {target['name']} has {max(0, target['hp'] - damage)} HP left.",
                color="important",
            )
            self.hit_enemy(target, damage)
            # a swift quiver keeps the arrows coming
            for _ in range(getattr(self, 'extra_shots', 0)):
                t = self.current_target()
                if not t:
                    break
                shot = random.randint(1, self.player_damage_dice) + self.player_damage_bonus
                self.log_message("Your quiver refills itself and you loose again.", color='important')
                self.hit_enemy(t, shot, 'piercing')
        else:
            self.play_sound('miss')
            if behind_cover and attack_total >= target['ac']:
                spot = self.obstacle[0] if getattr(self, 'obstacle', None) else 'its cover'
                self.log_message(f"{name} would have hit - but the shot smacks into {spot}!",
                                 color="warning")
            else:
                self.log_message(f"{name} misses the {target['name']}!", color="warning")

        # Your attack spends your ACTION and nothing else. The round stays
        # yours until you press End Turn, which is what lets you attack and
        # then still take a bonus action, use an item, or spend an extra
        # action from Haste.
        #
        # If you ever want attacking to end the turn again, call
        # self.end_turn() here instead of self.spend_action().
        self.spend_action()
        self.refresh_stats()
        self.refresh_inventory()
        self.refresh_buttons()
        self.prompt_end_of_turn()

    def do_quick_attack(self):
        """Accurate but light: +2 to hit, one damage die."""
        self.perform_combat_attack("Quick Attack", attack_bonus_mod=2, damage_dice_count=1)

    def do_heavy_attack(self):
        """Wild swing: -2 to hit, but two damage dice."""
        self.perform_combat_attack("Heavy Strike", attack_bonus_mod=-2, damage_dice_count=2)

    def do_precise_attack(self):
        """The balanced option: +1 to hit, one damage die."""
        self.perform_combat_attack("Precise Attack", attack_bonus_mod=1, damage_dice_count=1)

    def end_turn(self):
        """Deliberately hand the round over to the enemies.

        Nothing else does this - attacking and casting leave the turn with you.
        
"""
        if not self.in_combat:
            self.log_message("There is no combat to end.")
            return
        # consume player's remaining action/bonus and trigger enemy attack immediately
        self.player_action_available = False
        self.player_bonus_available = False
        # if enemy already pending, just resolve; otherwise set it and resolve
        self.enemy_attack_pending = True
        self.log_message("You end your turn. The enemies ready their attacks...", color="important")
        # your companion moves between you and them
        if self.companion_alive():
            self.companion_take_turn()
        # resolve immediately (the companion may have just ended the fight)
        self.resolve_enemy_attack()

    # ------------------------------------------------------------------ haste

    def start_haste(self, rounds=3):
        """Begin Haste: +2 AC and an extra action every round.

        The extra action is granted immediately so that casting it is not a wasted
        turn - you can cast Haste and still attack in the same round.
        
"""
        self.haste_rounds = rounds
        self.haste_active = True
        # you get the spare action straight away, so casting it isn't a wasted turn
        self.extra_action_available = True
        self.update_derived_stats()
        self.log_message(
            f"HASTE! You blur into motion: +2 AC and an extra action each round for {rounds} rounds.",
            color='important')

    def tick_haste(self):
        """Count Haste down at the start of your turn and hand out its extra action."""
        if not getattr(self, 'haste_active', False):
            return
        self.haste_rounds = getattr(self, 'haste_rounds', 0) - 1
        if self.haste_rounds <= 0:
            self.end_haste()
            return
        self.extra_action_available = True
        self.log_message(f"Haste: you have an extra action this round ({self.haste_rounds} rounds left).",
                         color='important')

    def end_haste(self, silent=False):
        """Clear Haste. Called when it expires, when a fight ends, and on death."""
        self.haste_active = False
        self.haste_rounds = 0
        self.extra_action_available = False
        self.update_derived_stats()
        if not silent:
            self.log_message("The Haste fades and the world catches up with you.")

    def spend_action(self):
        """Use up your action for the round.

        If Haste is granting a spare action, that gets eaten first and your real
        action survives. Everything that costs an action should call this rather
        than setting player_action_available directly, or Haste will not work.
        
"""
        if getattr(self, 'extra_action_available', False):
            self.extra_action_available = False
            self.log_message("Haste carries you onward: you still have an action this round!",
                             color='important')
            return
        self.player_action_available = False

    def prompt_end_of_turn(self):
        """Remind the player that the round is theirs until they end it."""
        if not self.in_combat or not self.living_enemies():
            return
        if getattr(self, 'enemy_attack_pending', False):
            return
        if self.player_action_available or self.player_bonus_available:
            left = []
            if self.player_action_available:
                left.append("action")
            if self.player_bonus_available:
                left.append("bonus action")
            self.log_message(f"You still have your {' and '.join(left)}. Press End Turn when you're done.")
        else:
            self.log_message("Nothing left this round \u2014 press End Turn.", color='important')

    def spend_bonus(self):
        """Try to spend your bonus action. Returns False (and complains) if it is gone."""
        if not self.player_bonus_available:
            self.log_message("That is a bonus action \u2014 yours is spent this round.")
            return False
        self.player_bonus_available = False
        return True

    # ----------------------------------------------------------- bonus actions

    def open_bonus_menu(self):
        """The bonus action menu.

        To add a new bonus action: add a button here and write a bonus_* method that
        finishes by setting self.player_bonus_available = False.
        
"""
        if not self.in_combat:
            self.log_message("Bonus actions are used in combat.")
            return
        if self.enemy_attack_pending:
            self.log_message("The enemies are still taking their turn.")
            return
        if not self.player_bonus_available:
            self.log_message("You've already used your bonus action this round.")
            return

        menu = self.make_popup("Bonus Action")
        frame = ttk.Frame(menu, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Choose a bonus action:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))

        def pick(action):
            menu.destroy()
            action()
            self.refresh_stats()
            self.refresh_buttons()

        ttk.Button(frame, text="Off-hand Strike \u2014 a quick 1d4 jab at your target",
                   command=lambda: pick(self.bonus_offhand_strike)).pack(fill=tk.X, pady=3)
        ttk.Button(frame, text="Defend \u2014 +2 AC until your next turn",
                   command=lambda: pick(self.bonus_defend)).pack(fill=tk.X, pady=3)
        ttk.Button(frame, text="Size Up the Enemy \u2014 learn its resistances and weaknesses",
                   command=lambda: pick(self.bonus_study)).pack(fill=tk.X, pady=3)
        if 'potion' in self.inventory:
            count = self.inventory.count('potion')
            ttk.Button(frame, text=f"Drink Potion \u2014 restore 2d4+2 HP  (x{count})",
                       command=lambda: pick(self.bonus_potion)).pack(fill=tk.X, pady=3)
        if self.inventory:
            ttk.Label(frame, text="Any item in your bag can be used as a bonus action \u2014 "
                                  "select it in the Inventory list and press Use Item.",
                      style='Dim.TLabel', wraplength=320, justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))
        if self.char_class == 'Fighter' and self.second_wind_available:
            ttk.Label(frame, text="Second Wind (in Class Ability) is also a bonus action.",
                      style='Dim.TLabel').pack(anchor=tk.W, pady=(4, 0))
        if self.char_class == 'Rogue' and self.sneak_available:
            ttk.Label(frame, text="Preparing Sneak Attack (in Class Ability) is also a bonus action.",
                      style='Dim.TLabel').pack(anchor=tk.W, pady=(4, 0))
        if self.class_spell_list():
            ttk.Label(frame, text="Spells marked [bonus] (Shield, Blur, Healing Word, Misty Step...) "
                                  "also use this.",
                      style='Dim.TLabel', wraplength=320, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(frame, text="Cancel", command=menu.destroy).pack(pady=(8, 0))
        self.place_window(menu, min_w=420, min_h=320)

    def bonus_offhand_strike(self):
        """A quick 1d4 jab - less damage than a real attack, but it is free."""
        target = self.current_target()
        if target is None:
            return
        penalty = 0
        if target.get('dist') == 'far':
            if getattr(self, 'player_move_available', True):
                self.player_move_available = False
                target['dist'] = 'near'
                self.player_in_cover = False
                self.log_message(f"You dart in at the {target['name']}.", color='player')
                self.draw_combat()
            else:
                penalty = 4
                self.log_message("It is well out of jab range - you stretch for it anyway (-4).",
                                 color='warning')
        roll = random.randint(1, 20)
        self.show_dice_roll(roll)
        total = roll + self.player_attack_bonus - penalty
        self.log_message(f"Off-hand Strike: attack roll {roll} + {self.player_attack_bonus} = {total}.", color="player")
        if roll == 20 or total >= target['ac']:
            dmg = random.randint(1, 4) * (2 if roll == 20 else 1)
            self.play_sound('crit' if roll == 20 else 'hit')
            if roll == 20:
                self.log_message("Critical off-hand strike!", color="important")
            self.hit_enemy(target, dmg, 'off-hand')
        else:
            self.play_sound('miss')
            self.log_message(f"Your off-hand strike misses the {target['name']}.", color="warning")
        self.player_bonus_available = False

    def bonus_defend(self):
        """Raise your guard for +2 AC until your next turn."""
        self.defend_active = True
        self.update_derived_stats()
        self.play_sound('success')
        self.log_message("You raise your guard: +2 AC until your next turn.", color="important")
        self.player_bonus_available = False

    def bonus_study(self):
        """Read your target properly: report exactly what it resists and what hurts it."""
        t = self.current_target()
        if t is None:
            return
        bits = [f"AC {t['ac']}", f"{t['hp']}/{t['max_hp']} HP",
                f"{t.get('attacks', 1)} attack{'s' if t.get('attacks', 1) != 1 else ''} a round",
                f"hits for up to {t['dmg']}"]
        self.log_message(f"You study the {t['name']}: {', '.join(bits)}.", color='player')
        if t.get('resist'):
            self.log_message(f"It takes half damage from {', '.join(t['resist'])}.", color='warning')
        if t.get('vulnerable'):
            self.log_message(f"It is badly hurt by {', '.join(t['vulnerable'])}.", color='important')
        if not t.get('resist') and not t.get('vulnerable'):
            self.log_message("Nothing about it looks especially resistant or fragile.")
        self.player_bonus_available = False

    def bonus_potion(self):
        """Drink a potion mid-fight."""
        if 'potion' not in self.inventory:
            self.log_message("You have no potion to drink.")
            return
        self.inventory.remove('potion')
        self.play_sound('potion')
        self.heal_player(random.randint(1, 4) + random.randint(1, 4) + 2,
                         "You gulp down a potion mid-fight")
        self.player_bonus_available = False
        self.refresh_inventory()
        self.refresh_stats()

    # ----------------------------------------------------------- your movement
    # One free move per round, refreshed in start_of_round. Attacking a far
    # target with a melee weapon uses it automatically (perform_combat_attack),
    # so this menu is for moving on purpose: closing without swinging, breaking
    # away from a pack, or getting behind the room's obstacle.

    def open_move_menu(self):
        """The movement menu: Close In, Fall Back, or Take Cover.

        To add a new move: add a button here and a do_* method that finishes by
        setting self.player_move_available = False.
        """
        if not self.in_combat:
            self.log_message("There is nowhere to move to outside a fight.")
            return
        if self.enemy_attack_pending:
            self.log_message("The enemies are still taking their turn.")
            return
        if not getattr(self, 'player_move_available', True):
            self.log_message("You have already moved this round.")
            return

        living = self.living_enemies()
        any_far = any(e.get('dist') == 'far' for e in living)
        any_near = any(e.get('dist') == 'near' for e in living)

        menu = self.make_popup("Move")
        frame = ttk.Frame(menu, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="One move per round. Spend it well:",
                  font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))

        def pick(action):
            menu.destroy()
            action()
            self.refresh_stats()
            self.refresh_buttons()

        if any_far:
            ttk.Button(frame, text="Close In \u2014 engage your target without attacking yet",
                       command=lambda: pick(self.do_close_in)).pack(fill=tk.X, pady=3)
        if any_near:
            swipe_note = ("they slip away clean" if self.char_class == 'Rogue'
                          else "each nearby enemy gets one parting swipe")
            ttk.Button(frame, text=f"Fall Back \u2014 open the distance from everything ({swipe_note})",
                       command=lambda: pick(self.do_fall_back)).pack(fill=tk.X, pady=3)
        if getattr(self, 'obstacle', None) and not getattr(self, 'player_in_cover', False):
            ttk.Button(frame, text=f"Take Cover \u2014 duck behind {self.obstacle[0]} "
                                   f"(+{COVER_AC} AC vs ranged, halves breath/quake)",
                       command=lambda: pick(self.do_take_cover)).pack(fill=tk.X, pady=3)
        if not any_far and not any_near and not getattr(self, 'obstacle', None):
            ttk.Label(frame, text="Nothing useful to do with your feet right now.",
                      style='Dim.TLabel').pack(anchor=tk.W)
        if getattr(self, 'player_in_cover', False):
            ttk.Label(frame, text="You are in cover. Melee swings and closing in will break it.",
                      style='Dim.TLabel', wraplength=360, justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))
        ttk.Button(frame, text="Cancel", command=menu.destroy).pack(pady=(8, 0))
        self.place_window(menu, min_w=430, min_h=240)

    def do_close_in(self):
        """Spend your move to engage your (far) target - no attack, no penalty."""
        if not self.in_combat or self.enemy_attack_pending:
            return
        if not getattr(self, 'player_move_available', True):
            self.log_message("You have already moved this round.")
            return
        target = self.current_target()
        if target is None or target.get('dist') != 'far':
            # closing on someone already in your face costs nothing
            far = [e for e in self.living_enemies() if e.get('dist') == 'far']
            if not far:
                self.log_message("Everything is already within reach.")
                return
            target = far[0]
            self.target_index = self.enemies.index(target)
        self.player_move_available = False
        target['dist'] = 'near'
        if getattr(self, 'player_in_cover', False):
            self.player_in_cover = False
            self.log_message(f"You break from cover and close on the {target['name']}.",
                             color='player')
        else:
            self.log_message(f"You close the distance to the {target['name']}.", color='player')
        self.draw_combat()

    def do_fall_back(self):
        """Open the distance from everything near you.

        Everyone you disengage from gets one parting swipe at -2 (for reduced
        damage) - unless you are a Rogue, whose cunning footwork is exactly for
        this. Skirmishers hate it: it strips pack tactics and forces the melee
        enemies to spend their turns closing again.
        """
        if not self.in_combat or self.enemy_attack_pending:
            return
        if not getattr(self, 'player_move_available', True):
            self.log_message("You have already moved this round.")
            return
        near = [e for e in self.living_enemies() if e.get('dist') == 'near']
        if not near:
            self.log_message("Nothing is close enough to fall back from.")
            return
        self.player_move_available = False
        if self.char_class == 'Rogue':
            self.log_message("Cunning footwork: you slip out of reach without a scratch.",
                             color='player')
        else:
            for e in near:
                roll = random.randint(1, 20)
                total = roll + e['atk'] - 2 + self.enemy_attack_penalty
                if total >= self.player_ac:
                    dmg = random.randint(1, max(2, e['dmg'] // 2))
                    self.play_sound('enemy_hit')
                    self.damage_player(dmg, f"The {e['name']} gets a parting swipe in as you "
                                            f"disengage. ({roll} +{e['atk'] - 2} = {total})")
                    if self.health <= 0:
                        self.hide_combat_panel()
                        self.handle_death()
                        return
                else:
                    self.log_message(f"The {e['name']} snatches at you and misses as you pull "
                                     f"away. ({roll} +{e['atk'] - 2} = {total})", color='enemy')
        for e in near:
            e['dist'] = 'far'
        self.log_message("You open the distance - everything is at range now.", color='player')
        self.draw_combat()
        self.refresh_stats()

    def do_take_cover(self):
        """Spend your move getting behind the room's obstacle."""
        if not self.in_combat or self.enemy_attack_pending:
            return
        if not getattr(self, 'player_move_available', True):
            self.log_message("You have already moved this round.")
            return
        if not getattr(self, 'obstacle', None):
            self.log_message("There is nothing here worth hiding behind.")
            return
        if getattr(self, 'player_in_cover', False):
            self.log_message("You are already in cover.")
            return
        self.player_move_available = False
        self.player_in_cover = True
        self.play_sound('success')
        self.log_message(f"You duck behind {self.obstacle[0]}: +{COVER_AC} AC against ranged "
                         "attacks, and half damage from a boss's breath or quake. Melee swings "
                         "and closing in will break it.", color='important')
        self.draw_combat()
        self.refresh_stats()

    # ------------------------------------------------------ adaptive difficulty
    # A quiet dial turned by how your last few fights went. It nudges the pack
    # HP budget (make_enemy_pack) and the item drop chance (defeat_enemy) inside
    # tight bounds from data.py. Toggle in Settings; saved with the character.

    def record_fight_result(self, died):
        """Remember how a fight went: HP lost, rounds taken, whether you died."""
        if not hasattr(self, 'recent_fights'):
            self.recent_fights = []
        start = getattr(self, '_fight_hp_start', self.health)
        max_hp = max(1, getattr(self, 'max_health', 1))
        frac = 1.0 if died else max(0.0, min(1.0, (start - self.health) / max_hp))
        self.recent_fights.append({'frac': round(frac, 3), 'died': bool(died),
                                   'rounds': getattr(self, '_fight_round_count', 0)})
        del self.recent_fights[:-ADAPTIVE_WINDOW]
        self.update_adaptive()

    def update_adaptive(self):
        """Re-aim the dial: struggle eases packs off, cruising firms them up."""
        if not getattr(self, 'adaptive_enabled', True) or not getattr(self, 'recent_fights', None):
            return
        rec = self.recent_fights
        n = len(rec)
        pressure = (sum(r['frac'] for r in rec) / n
                    + 0.5 * sum(1 for r in rec if r['died']) / n
                    + 0.2 * sum(1 for r in rec if r['rounds'] >= 9) / n)
        mult = getattr(self, 'adaptive_mult', 1.0)
        if pressure > 0.6:
            mult -= ADAPTIVE_STEP
        elif pressure < 0.22:
            mult += ADAPTIVE_STEP
        self.adaptive_mult = max(ADAPTIVE_MIN, min(ADAPTIVE_MAX, mult))

    # ---------------------------------------------------------- making enemies

    def make_enemy_pack(self, floor, count=None):
        """Build a group of enemies scaled to the dungeon floor.

        Deeper floors get tougher enemy types and more of them. Difficulty settings
        scale HP and attack on top of that. Add new enemy types to the table here -
        each entry is (name, resistances, vulnerabilities).
        
"""
        diff = DIFFICULTIES.get(getattr(self, 'difficulty', 'Normal'), DIFFICULTIES['Normal'])
        tiers = [
            [('goblin', [], []), ('giant rat', [], []), ('kobold', [], ['fire']),
             ('giant spider', ['poison'], ['fire']), ('skeleton', ['necrotic'], ['radiant']),
             ('zombie', ['necrotic'], ['radiant', 'fire'])],
            [('orc', [], []), ('ghost', ['necrotic', 'poison'], ['radiant']),
             ('cultist', [], ['radiant']), ('gnoll', [], []),
             ('harpy', [], ['thunder']), ('animated armor', ['poison', 'necrotic'], ['thunder'])],
            [('troll', [], ['fire', 'acid']), ('wraith', ['necrotic', 'cold'], ['radiant']),
             ('ogre', [], []), ('basilisk', ['poison'], ['radiant']),
             ('minotaur', [], []), ('hell hound', ['fire'], ['cold'])],
            [('fire elemental', ['fire', 'poison'], ['cold']),
             ('stone golem', ['fire', 'lightning', 'poison'], ['thunder']),
             ('young wyrm', ['fire', 'necrotic'], ['cold']),
             ('minotaur', [], []), ('wraith', ['necrotic', 'cold'], ['radiant'])],
        ]
        tier = min(len(tiers) - 1, (floor - 1) // 2)
        if count is None:
            # capped at three: a fourth attacker every round was what made deep
            # floors unsurvivable for low-AC classes, without making fights
            # more interesting. The pack budget still grows with the floor.
            max_count = min(3, 1 + (floor + 1) // 2)  # floor 1: up to 2, floor 3+: up to 3
            count = random.randint(1, max_count)
        # a distracting illusion can lure one enemy away from a pack
        if getattr(self, 'illusion_lure', False) and count > 1:
            count -= 1
            self.illusion_lure = False
            self.log_message("Your minor illusion lures one of the enemies away!", color='important')
        # a pack shares a health budget, so groups are individually weaker;
        # the budget and its per-floor growth are dials in data.py
        budget = random.randint(*PACK_HP_BUDGET) + (floor - 1) * PACK_HP_PER_FLOOR
        # the adaptive dial (see update_adaptive) quietly thins or firms packs
        # from how your last few fights went - bounded, and off in Settings
        if getattr(self, 'adaptive_enabled', True):
            budget = max(10, int(budget * getattr(self, 'adaptive_mult', 1.0)))
        pack = []
        for _ in range(count):
            name, resist, vulnerable = random.choice(tiers[tier])
            hp = max(6, int((budget // count + random.randint(-2, 3)) * diff['enemy_hp']))
            ranged = name in RANGED_ENEMIES
            pack.append({
                'name': name,
                'hp': hp, 'max_hp': hp,
                'ac': random.randint(11, 14) + (floor - 1) // 2,
                # to-hit grows every 3 floors, not 2: your AC barely scales, so
                # the old rate quietly pushed deep-floor hit rates past 60%
                'atk': max(0, 2 + (floor - 1) // 3 + diff['enemy_atk']),
                'dmg': 6 + (floor // 3),
                'held': False,
                'charmed': False,
                'burning': 0,
                'attacks': 1,
                'boss': False,
                'resist': list(resist),
                'vulnerable': list(vulnerable),
                # tactics: skirmishers shoot from range and may fall back once;
                # the mindless never make morale checks
                'ranged': ranged,
                'dist': 'far' if ranged else 'near',
                'in_cover': False,
                'retreats_left': 1,
                'fearless': name in FEARLESS_ENEMIES,
            })
        return pack

    def make_boss(self, floor):
        """Build the boss for a floor, plus whatever minions it brings.

        Bosses come from the BOSSES table in data.py; which one you meet depends on
        how deep you are. Their statistics scale with the floor on top of that, so
        the same boss on floor 12 is a very different proposition from floor 3.
        
"""
        diff = DIFFICULTIES.get(getattr(self, 'difficulty', 'Normal'), DIFFICULTIES['Normal'])
        tier = min(2, max(0, (floor - 1) // (BOSS_EVERY * 2)))
        candidates = [(name, info) for name, info in BOSSES.items() if info['tier'] == tier]
        if not candidates:
            candidates = list(BOSSES.items())
        name, info = random.choice(candidates)

        scale = 1.0 + BOSS_HP_SCALE * max(0, floor - 1)
        hp = int(info['hp'] * scale * diff['enemy_hp'])
        boss = {
            'name': name,
            'hp': hp, 'max_hp': hp,
            'ac': info['ac'] + (floor - 1) // 4,
            'atk': info['atk'] + (floor - 1) // 3 + diff['enemy_atk'],
            'dmg': info['dmg'],
            'attacks': info['attacks'],
            'held': False,
            'charmed': False,
            'burning': 0,
            'boss': True,
            'special': info['special'],
            'cooldown': 1,
            'cooldown_max': 3,
            'enraged': False,
            'ranged': False,
            'dist': 'near',
            'in_cover': False,
            'retreats_left': 0,
            'fearless': True,
            'drains': info['special'] == 'drain',
            'resist': list(info['resist']),
            'vulnerable': list(info['vulnerable']),
            'loot': info['loot'],
            'title': info['title'],
        }
        pack = [boss]
        for _ in range(info.get('minions', 0)):
            minion = self.make_enemy_pack(floor, count=1)[0]
            minion['hp'] = max(6, minion['hp'] // 2)
            minion['max_hp'] = minion['hp']
            pack.append(minion)
        return pack
