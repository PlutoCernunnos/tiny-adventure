"""Companions: one hired ally who fights beside you.

Hired at any shop (one at a time), gone for good at 0 HP. Their numbers and
archetypes are pure data - COMPANIONS in data.py - and this file is the brain:
what they do with their turn, and how enemies treat them.

HOW THEIR TURN WORKS
    end_turn() in combat.py calls companion_take_turn() after you hand the
    round over and before the enemies move. The brain is a short priority
    list: a healer patches you up when you are hurting, anyone badly hurt
    ducks behind cover if there is any, and otherwise they focus the weakest
    living enemy so the pack thins out fast.

HOW ENEMIES TREAT THEM
    enemy_single_attack() in combat.py asks companion_should_intercept()
    before every enemy swing. A sellsword draws over half the attacks aimed
    at you on purpose; the others soak some too, less if they are in cover.
    The swing is then resolved against the companion's own AC and HP.

Everything reads self.player_level, so a companion hired at level 2 keeps up
as you level - no separate XP to manage.
"""
import random
import tkinter as tk
from tkinter import ttk

from .data import (COMPANIONS, COMPANION_NAMES, COMPANION_HIRE_PER_FLOOR,
                   COVER_AC)


class CompanionMixin:

    # ------------------------------------------------------------- basics

    def companion_alive(self):
        """True while you have a companion and they are still standing."""
        c = getattr(self, 'companion', None)
        return bool(c and c.get('hp', 0) > 0)

    def companion_info(self):
        """The COMPANIONS data row for your current companion (or {})."""
        c = getattr(self, 'companion', None)
        return COMPANIONS.get(c['kind'], {}) if c else {}

    def companion_max_hp(self):
        """Max HP scales with YOUR level, so an old hire keeps up."""
        info = self.companion_info()
        return (info.get('hp', 10)
                + info.get('per_level', 4) * max(0, getattr(self, 'player_level', 1) - 1))

    def companion_ac(self):
        """Armour class, plus cover if they have ducked behind something."""
        info = self.companion_info()
        ac = info.get('ac', 12) + getattr(self, 'player_level', 1) // 4
        c = getattr(self, 'companion', None)
        if c and c.get('in_cover'):
            ac += COVER_AC
        return ac

    def companion_hire_price(self, kind):
        """What this archetype costs to hire on the current floor."""
        info = COMPANIONS[kind]
        return info.get('hire', 45) + COMPANION_HIRE_PER_FLOOR * max(0, self.current_floor() - 1)

    # -------------------------------------------------------------- hiring

    def hire_companion(self, kind, free=False):
        """Take an archetype on. Pays gold unless free=True (rescues, tests)."""
        if kind not in COMPANIONS:
            return False
        if getattr(self, 'companion', None):
            self.log_message("You already travel with someone. One companion at a time.",
                             color='warning')
            return False
        price = 0 if free else self.companion_hire_price(kind)
        if self.gold < price:
            self.log_message(f"Hiring the {COMPANIONS[kind]['title'].lower()} costs {price} gold "
                             "- more than you have.", color='warning')
            return False
        self.gold -= price
        info = COMPANIONS[kind]
        self.companion = {
            'kind': kind,
            'title': info['title'],
            'name': random.choice(COMPANION_NAMES),
            'hp': self.companion_max_hp() if hasattr(self, 'player_level') else info['hp'],
            'in_cover': False,
        }
        # companion_max_hp reads companion_info, which needs self.companion set
        self.companion['hp'] = self.companion_max_hp()
        self.play_sound('coin')
        self.log_message(f"{self.companion['name']} the {info['title']} shoulders their gear "
                         f"and falls in beside you."
                         + (f" (-{price} gold)" if price else ""), color='important')
        self.refresh_stats()
        return True

    def open_hire_menu(self, parent=None, on_hired=None):
        """The hiring board: every archetype, its price here, and what it does."""
        if getattr(self, 'companion', None):
            self.log_message(f"{self.companion['name']} is already with you. "
                             "One companion at a time.", color='warning')
            return
        win = self.make_popup("Hire a Companion")
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Swords (and needles) for hire",
                  font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(frm, text="One companion at a time. They fight after you end your turn, "
                            "draw some attacks off you, and scale with your level. "
                            "At 0 HP they are gone for good.",
                  style='Dim.TLabel', wraplength=430, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 8))

        def hire(kind):
            if self.hire_companion(kind):
                win.destroy()
                if on_hired:
                    try:
                        on_hired()
                    except Exception:
                        pass

        for kind, info in COMPANIONS.items():
            price = self.companion_hire_price(kind)
            box = ttk.Frame(frm)
            box.pack(fill=tk.X, pady=3)
            row = ttk.Frame(box)
            row.pack(fill=tk.X)
            ttk.Label(row, text=info['title'], font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
            ttk.Button(row, text=f"Hire ({price}g)",
                       command=lambda k=kind: hire(k)).pack(side=tk.RIGHT)
            ttk.Label(box, text=info['desc'], style='Dim.TLabel',
                      wraplength=430, justify=tk.LEFT).pack(anchor=tk.W, padx=(6, 0))
        ttk.Button(frm, text="Not today", command=win.destroy).pack(pady=(10, 0))
        self.place_window(win, min_w=470, min_h=380)

    # ---------------------------------------------------- their turn brain

    def companion_take_turn(self):
        """The companion acts: heal, duck into cover, or hit the weakest enemy.

        Called by end_turn() after you hand the round over, before the enemies
        move. Deliberately simple and readable - a short priority list, not a
        planner - so what they do is always explainable from the log.
        """
        if not self.in_combat or not self.companion_alive():
            return
        c = self.companion
        info = self.companion_info()
        style = info.get('style', 'striker')
        alive = self.living_enemies()
        if not alive:
            return

        # 1. badly hurt and there is something to hide behind: use it
        if (getattr(self, 'obstacle', None) and not c.get('in_cover')
                and c['hp'] <= self.companion_max_hp() * 0.3 and style != 'healer'):
            c['in_cover'] = True
            self.log_message(f"{c['name']} ducks behind {self.obstacle[0]}, breathing hard.",
                             color='important')
            self.draw_combat()
            return

        # 2. a medic patches you up when you are genuinely hurting
        if style == 'healer' and self.health < 0.6 * self.max_health:
            amount = random.randint(1, 6) + max(1, self.player_level // 2)
            self.play_sound('potion')
            self.heal_player(amount, f"{c['name']} presses a field dressing to your wounds")
            return

        # 3. otherwise: focus the weakest living enemy so the pack thins fast
        minions = [e for e in alive if not e.get('boss')]
        target = min(minions or alive, key=lambda e: e['hp'])

        to_hit = 2 + info.get('atk', 1) + self.player_level // 4
        roll = random.randint(1, 20)
        total = roll + to_hit
        crit = roll == 20
        verb = {
            'tank': 'wades in on', 'striker': 'looses an arrow at',
            'caster': 'snaps a mote of fire at', 'healer': 'darts in and jabs',
        }.get(style, 'strikes at')
        if crit or total >= target['ac']:
            dmg = random.randint(1, info.get('die', 6)) + self.player_level // 3
            if crit:
                dmg += random.randint(1, info.get('die', 6))
            self.play_sound('crit' if crit else 'hit')
            self.log_message(f"{c['name']} {verb} the {target['name']}"
                             f"{' - a perfect strike!' if crit else '.'} "
                             f"({roll} +{to_hit} = {total})", color='player')
            self.hit_enemy(target, dmg, info.get('dmg_type', ''),
                           attacker=c['name'])
        else:
            self.play_sound('miss')
            self.log_message(f"{c['name']} {verb} the {target['name']} and misses. "
                             f"({roll} +{to_hit} = {total})", color='warning')

    # -------------------------------------------------- soaking enemy hits

    def companion_should_intercept(self, enemy):
        """Does this enemy swing at your companion instead of you?

        A sellsword draws over half of everything on purpose; the others soak
        less, and being in cover makes ranged attackers look elsewhere.
        """
        if not self.companion_alive() or not self.in_combat:
            return False
        style = self.companion_info().get('style')
        chance = 0.55 if style == 'tank' else 0.30
        if enemy.get('ranged') and enemy.get('dist') == 'far':
            chance -= 0.05
            if self.companion.get('in_cover'):
                chance -= 0.15
        return random.random() < max(0.0, chance)

    def companion_absorb_attack(self, enemy):
        """Resolve one enemy attack against the companion instead of you.

        Returns True always: the player cannot die from an attack they did not
        take, so the enemy turn continues normally.
        """
        c = self.companion
        roll = random.randint(1, 20)
        total = roll + enemy['atk'] + self.enemy_attack_penalty
        ac = self.companion_ac()
        if total >= ac:
            dmg = random.randint(1, enemy['dmg'])
            self.play_sound('enemy_hit')
            self.log_message(f"The {enemy['name']} turns on {c['name']} and hits for {dmg}. "
                             f"({roll} +{enemy['atk']} = {total})", color='enemy')
            self.damage_companion(dmg, enemy['name'])
        else:
            self.log_message(f"The {enemy['name']} swings at {c['name']} and misses. "
                             f"({roll} +{enemy['atk']} = {total})", color='enemy')
        return True

    def damage_companion(self, amount, source):
        """Hurt the companion; at 0 HP they are gone for good."""
        c = getattr(self, 'companion', None)
        if not c:
            return
        c['hp'] = max(0, c['hp'] - amount)
        if c['hp'] <= 0:
            self.play_sound('death')
            self.log_message(f"{c['name']} the {c['title']} goes down and does not get up. "
                             "You will have to finish this alone.", color='warning')
            self.narrate(f"{c['name']} is down.")
            self.companion = None
        self.refresh_stats()
        self.draw_combat()

    def heal_companion(self, amount):
        """Patch the companion up (long rests and camps call this)."""
        c = getattr(self, 'companion', None)
        if not c:
            return 0
        healed = min(self.companion_max_hp() - c['hp'], max(0, amount))
        c['hp'] += healed
        return healed
