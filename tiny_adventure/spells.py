"""Spellcasting, upcasting, and the spellbook.

cast_spell() is one long chain of `if spell_key == ...` branches, one per
spell. That is deliberate - each spell reads as a self-contained recipe, and
adding one means adding a branch rather than understanding a framework.

ADDING A SPELL - all four steps are needed

    1. data.py  SPELL_CATALOG   name, description, level, action or bonus
    2. data.py  CLASS_SPELLS    which classes may learn it
    3. here     a branch in cast_spell that does the thing
    4. data.py  OUT_OF_COMBAT_SPELLS, if it works while exploring
    5. data.py  SPELL_UPCAST, if a bigger slot should do more

Miss step 3 and the spell still casts, but falls through to a generic damage
effect at the bottom of the chain.

UPCASTING
cast_spell takes `level`: the level of the SLOT being spent, which may be
higher than the spell's own level. Inside a branch:

    spell_level   the spell's own level, from the catalog
    level         the slot actually being spent
    upcast        the difference - 0 when cast normally

So Fireball rolls `8 + upcast` dice, Magic Missile fires `3 + upcast` darts,
and Cure Wounds heals `1 + upcast` extra dice. The spellbook draws one button
per slot level you could spend, so upcasting is a click, not a menu.

CANTRIPS scale with your character level instead, through cantrip_dice() in
character.py: one die, then two at level 5, three at 11, four at 17.

THE HELPERS available inside cast_spell (defined near the top of it)

    consume_action()      spend the action or bonus this spell costs
    dice(n, d)            roll n dice of d sides and total them
    damage_enemy(n, kind) damage the current target, rolling to hit
    damage_all(n, kind)   damage every enemy, with a save for half
    spell_attack(target)  roll to hit and report it
    enemy_saves(target)   True if the enemy resists
    living()              every enemy still standing
    heal(n)               heal the caster, respecting Beacon of Hope
    linger(n, d, kind, r) leave an effect burning for r more rounds

Always finish a branch with consume_action() and `return True`.

ORDER OF CHECKS at the top of cast_spell, before anything is spent: your class
must know the spell, the spell must work in this situation, you must have the
action or bonus free, and only then is a slot deducted. That ordering is what
guarantees a refused spell never costs you a slot.

SCROLLS call this with from_scroll=True, which skips the class check, the slot
cost and the action cost - the scroll itself already paid for all three.
"""
import os
import json
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, filedialog, messagebox

from .data import (WEAPONS, FINESSE, ARMOR, SHIELDS, MAGIC_ITEMS, CLASSES,
                   DIFFICULTIES, CLASS_SPELLS, SPELL_LEVELS, SPELL_UPCAST,
                   OUT_OF_COMBAT_SPELLS, CLASS_STAT_PRIORITY, STARTING_KIT,
                   ITEM_INFO, SPELL_CATALOG)
from .audio import (SOUND_DEFS, MUSIC_MOVEMENTS, MciAudio, write_sound_file,
                    write_music_file, winsound)
from .paths import game_dir


class SpellsMixin:

    # Roughly how many enemies each area spell can realistically catch.
    AOE_LIMITS = {
        'acid_splash': 2, 'burning_hands': 3, 'thunderwave': 3, 'shatter': 4,
        'fireball': 6, 'lightning_bolt': 6, 'stinking_cloud': 5,
        'conjure_barrage': 5, 'spirit_guardians': 5, 'ice_storm': 6,
        'wall_of_fire': 4, 'cone_of_cold': 6, 'flame_strike': 5,
        'destructive_wave': 6, 'insect_plague': 5, 'soul_harvest': 5,
        'call_lightning': 4, 'sleet_storm': 5, 'guardian_of_flame': 4,
    }

    def cast_spell(self, spell_key, level=1, from_scroll=False):
        """Cast one spell by key. Returns True if it actually went off.

        Checks in order - class list, combat context, action economy, slot - so that
        a refused spell never costs you anything. Each spell is then a branch below;
        see the module docstring at the top of this file for how to add one.

        `level` is which slot level to spend, and may be higher than the spell's own
        level: that is upcasting, and `upcast` below is the difference. 0 means a
        cantrip, which is free.

        `from_scroll` is for reading a scroll: no class restriction, no slot, and no
        action cost, because the scroll has already covered all three.
        
"""
        name, desc, spell_level, action_type = self.spell_catalog.get(
            spell_key, (None, None, level, 'action'))
        # casting from a bigger slot than the spell needs is upcasting
        level = max(level, spell_level)
        upcast = max(0, level - spell_level)

        # your class has to actually have this spell on its list
        if not from_scroll and spell_key not in self.class_spell_list():
            self.log_message(f"A {getattr(self, 'char_class', 'character')} cannot cast {name or spell_key}.")
            return False

        # some spells simply have nothing to do with no enemies around; refuse
        # them here so the slot is never spent for nothing
        if not self.in_combat and spell_key not in OUT_OF_COMBAT_SPELLS:
            self.log_message(f"{name or spell_key} needs a target \u2014 save it for a fight.")
            return False

        # check action/bonus availability (the action economy only applies in a fight)
        if self.in_combat and not from_scroll:
            if action_type == 'action' and not getattr(self, 'player_action_available', True):
                self.log_message("No action available to cast that spell this round.")
                return False
            if action_type == 'bonus' and not getattr(self, 'player_bonus_available', True):
                self.log_message("No bonus action available to cast that spell this round.")
                return False

        # Level 0 is a cantrip and costs nothing. Note this deduction happens
        # AFTER every check above has passed, which is what guarantees a
        # refused spell never costs you a slot.
        if level > 0 and not from_scroll:
            slots = self.spell_slots_by_level.get(level, 0)
            if slots <= 0:
                self.log_message(f"No level {level} spell slots available.")
                return False
            self.spell_slots_by_level[level] = slots - 1
            if upcast:
                self.log_message(f"You pour a level {level} slot into {name or spell_key}.",
                                 color='important')

        # ------------------------------------------------------------ helpers
        def consume_action():
            self.play_sound('spell')
            if self.in_combat and not from_scroll:
                if action_type == 'action':
                    self.spend_action()
                elif action_type == 'bonus':
                    self.player_bonus_available = False
            # update pips/buttons immediately so the spent action shows at once
            self.refresh_stats()
            self.refresh_buttons()

        def refund():
            """Give the slot back - for spells that turn out to have nothing to do."""
            if level > 0 and not from_scroll:
                self.spell_slots_by_level[level] = self.spell_slots_by_level.get(level, 0) + 1

        def dice(count, sides):
            return sum(random.randint(1, sides) for _ in range(max(0, count)))

        # Spellcasting math: attack rolls for targeted spells, saves for blasts
        cast_stat = getattr(self, 'cast_stat', None) or 'intelligence'
        cast_mod = self.ability_mod(cast_stat)
        gear_spell = self.gear_effects().get('spell_atk', 0)
        # proficiency (character.py) rather than a flat +2, so spell attacks
        # keep landing at depth exactly like weapon attacks do
        spell_atk = self.proficiency_bonus() + cast_mod + gear_spell
        spell_dc = 10 + cast_mod + gear_spell
        cantrip_n = self.cantrip_dice()

        def living():
            return self.living_enemies() if self.in_combat else []

        def spell_attack(target):
            roll = random.randint(1, 20)
            self.show_dice_roll(roll)
            total = roll + spell_atk
            hit = roll == 20 or total >= target['ac']
            self.log_message(
                f"Spell attack vs {target['name']}: {roll} + {spell_atk} = {total} \u2014 {'hit!' if hit else 'miss.'}",
                color='player' if hit else 'warning')
            if not hit:
                self.play_sound('miss')
            return hit

        def enemy_saves(target):
            # Enemies don't track individual saves; a simple roll against your DC.
            # Bosses are noticeably better at shrugging things off.
            bonus = 2 + (4 if target.get('boss') else 0)
            roll = random.randint(1, 20) + bonus + upcast * -1
            return roll >= spell_dc

        def damage_enemy(amount, kind="", auto_hit=False):
            t = self.current_target() if self.in_combat else None
            if t:
                if auto_hit or spell_attack(t):
                    self.hit_enemy(t, amount, kind)

        def save_or_damage(amount, kind="", half_on_save=True):
            """One target, saving throw instead of an attack roll."""
            t = self.current_target() if self.in_combat else None
            if not t:
                return
            if enemy_saves(t):
                if half_on_save:
                    self.log_message(f"The {t['name']} braces against it (save vs DC {spell_dc}): half damage.",
                                     color='enemy')
                    self.hit_enemy(t, max(1, amount // 2), kind)
                else:
                    self.log_message(f"The {t['name']} resists {name or spell_key} (save vs DC {spell_dc}).",
                                     color='enemy')
            else:
                self.hit_enemy(t, amount, kind)

        def damage_all(amount, kind="", save_for_half=True):
            targets = living()
            limit = self.AOE_LIMITS.get(spell_key)
            if limit and len(targets) > limit:
                # pick a representative subset that the area would hit
                targets = random.sample(targets, limit)
            if len(targets) > 1:
                self.log_message("The blast engulfs the room!", color='important')
            for en in list(targets):
                dealt = amount
                if save_for_half and enemy_saves(en):
                    dealt = max(1, amount // 2)
                    self.log_message(f"The {en['name']} dives aside (save vs DC {spell_dc}): half damage.", color='enemy')
                self.hit_enemy(en, dealt, kind)

        def heal(amount, flavour=None):
            return self.heal_player(amount, flavour or f"You cast {name or spell_key}")

        def linger(count, sides, kind, rounds, label):
            """Leave an area effect running for a few more rounds (see start_of_round)."""
            if not hasattr(self, 'lingering') or self.lingering is None:
                self.lingering = []
            self.lingering.append({'count': count, 'sides': sides, 'kind': kind,
                                   'rounds': rounds, 'label': label})

        def hold_targets(count, note):
            """Hold up to `count` enemies that fail their save. Returns how many stuck."""
            caught = 0
            for en in living():
                if caught >= count:
                    break
                if not enemy_saves(en):
                    en['held'] = True
                    caught += 1
            if caught:
                self.log_message(f"{note} {caught} enem{'y is' if caught == 1 else 'ies are'} "
                                 "caught and will miss the next turn.", color='important')
            else:
                self.log_message(f"{note} Nothing is held.")
            self.draw_combat()
            return caught

        # ====================================================== CANTRIPS ====
        if spell_key in ('ray_of_frost', 'fire_bolt', 'shocking_grasp', 'chill_touch',
                         'thorn_whip', 'eldritch_blast', 'produce_flame'):
            table = {'ray_of_frost': (8, 'cold'), 'fire_bolt': (10, 'fire'),
                     'shocking_grasp': (8, 'lightning'), 'chill_touch': (8, 'necrotic'),
                     'thorn_whip': (6, 'piercing'), 'eldritch_blast': (10, 'force'),
                     'produce_flame': (8, 'fire')}
            sides, kind = table[spell_key]
            self.log_message(f"You cast {name or spell_key}.")
            if spell_key == 'eldritch_blast':
                # one beam per cantrip die, each rolled to hit separately
                for beam in range(cantrip_n):
                    t = self.current_target()
                    if not t:
                        break
                    if cantrip_n > 1:
                        self.log_message(f"Beam {beam + 1} of {cantrip_n}:")
                    if spell_attack(t):
                        self.hit_enemy(t, random.randint(1, sides), kind)
            else:
                damage_enemy(dice(cantrip_n, sides), kind)
            if spell_key == 'produce_flame':
                self.lantern_active = True
                self.log_message("The flame hovers over your palm and lights the room.")
            if spell_key == 'chill_touch':
                t = self.current_target()
                if t:
                    t['no_heal'] = True
            consume_action()
            return True

        if spell_key == 'poison_spray':
            self.log_message("A puff of sickly green mist billows into your target's face.")
            save_or_damage(dice(cantrip_n, 12), 'poison', half_on_save=False)
            consume_action()
            return True

        if spell_key == 'toll_the_dead':
            t = self.current_target() if self.in_combat else None
            wounded = bool(t and t['hp'] < t['max_hp'])
            sides = 12 if wounded else 8
            self.log_message("A mournful bell tolls somewhere just behind your target."
                             + (" It is already hurt - the bell rings louder." if wounded else ""))
            save_or_damage(dice(cantrip_n, sides), 'necrotic', half_on_save=False)
            consume_action()
            return True

        if spell_key == 'acid_splash':
            self.log_message("You hurl a bubble of acid that bursts over the enemies!")
            damage_all(dice(cantrip_n, 6), 'acid')
            consume_action()
            return True

        if spell_key == 'sacred_flame':
            self.log_message("You call down radiant fire; there is nowhere to hide from it.")
            save_or_damage(dice(cantrip_n, 8), 'radiant', half_on_save=False)
            consume_action()
            return True

        if spell_key == 'vicious_mockery':
            t = self.current_target() if self.in_combat else None
            self.log_message("You say something unforgivable, and mean it.")
            if t:
                if not enemy_saves(t):
                    self.enemy_attack_penalty = min(self.enemy_attack_penalty, -2)
                    self.log_message(f"The {t['name']} flinches: -2 to enemy attacks this round.",
                                     color='important')
                self.hit_enemy(t, dice(cantrip_n, 4), 'psychic')
            consume_action()
            return True

        if spell_key == 'guidance':
            self.guidance_ready = True
            self.log_message("A steadying touch: your next ability check gains 1d4.", color='important')
            consume_action()
            return True

        if spell_key == 'message':
            revealed = self.reveal_adjacent_rooms()
            if revealed:
                self.log_message(f"Your whisper carries down the corridors and comes back with "
                                 f"the shape of {revealed} room{'s' if revealed != 1 else ''}.",
                                 color='important')
            else:
                self.log_message("Your whisper comes back with nothing new.")
            consume_action()
            return True

        if spell_key == 'light':
            revealed = self.reveal_adjacent_rooms()
            self.lantern_active = True
            msg = "A bright mote of light blooms above your palm (+1 on your next attack)."
            if revealed:
                msg += f" It shines into {revealed} adjoining room{'s' if revealed != 1 else ''}!"
            self.log_message(msg, color='important')
            consume_action()
            return True

        if spell_key == 'mage_hand':
            self.mage_hand_ready = True
            self.log_message("A spectral hand drifts beside you \u2014 it will spring the next trap "
                             "you find from a safe distance.", color='important')
            consume_action()
            return True

        if spell_key == 'minor_illusion':
            self.illusion_lure = True
            self.log_message("You prepare a distracting illusion \u2014 the next enemy pack will be "
                             "one foe smaller.", color='important')
            consume_action()
            return True

        if spell_key == 'prestidigitation':
            heal(2, "You clean your gear and warm your hands")
            consume_action()
            return True

        if spell_key == 'true_strike':
            self.true_strike_bonus = getattr(self, 'true_strike_bonus', 0) + 2
            self.log_message("True Strike: your next attack gains +2 to hit.", color='important')
            consume_action()
            return True

        # ======================================================= LEVEL 1 ====
        if spell_key == 'magic_missile':
            darts = [random.randint(1, 4) + 1 for _ in range(3 + upcast)]
            total = sum(darts)
            self.log_message(f"Magic Missile darts streak out unerringly: {darts} -> {total} total.")
            damage_enemy(total, 'force', auto_hit=True)
            consume_action()
            return True

        if spell_key == 'burning_hands':
            self.log_message("A fan of flames erupts from your fingertips!")
            damage_all(dice(3 + upcast, 6), 'fire')
            consume_action()
            return True

        if spell_key == 'chromatic_orb':
            # the orb takes whatever form your target likes least
            t = self.current_target() if self.in_combat else None
            element = 'fire'
            if t and t.get('vulnerable'):
                element = t['vulnerable'][0]
            elif t and 'fire' in [r.lower() for r in t.get('resist', [])]:
                element = 'force'
            self.log_message(f"The orb settles into {element} as it leaves your hand.")
            damage_enemy(dice(3 + upcast, 8), element)
            consume_action()
            return True

        if spell_key == 'witch_bolt':
            self.log_message("A crackling tether snaps out and takes hold.")
            damage_enemy(dice(2 + upcast, 12), 'lightning')
            consume_action()
            return True

        if spell_key == 'thunderwave':
            self.log_message("A wave of thunderous force sweeps out from you!")
            damage_all(dice(2 + upcast, 8), 'thunder')
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -1)
            consume_action()
            return True

        if spell_key == 'shield_bolt':
            self.log_message("A bolt of shimmering force slams into your target.")
            damage_enemy(dice(1 + upcast, 8), 'force')
            consume_action()
            return True

        if spell_key == 'cure_wounds':
            heal(dice(1 + upcast, 8) + cast_mod)
            consume_action()
            return True

        if spell_key == 'healing_word':
            heal(dice(1 + upcast, 4) + cast_mod, "A word of power knits you back together")
            consume_action()
            return True

        if spell_key == 'goodberry':
            berries = 4 + upcast * 2
            for _ in range(berries):
                self.inventory.append('healing herbs')
            self.log_message(f"You conjure {berries} plump berries. (+{berries} healing herbs)",
                             color='important')
            self.refresh_inventory()
            consume_action()
            return True

        if spell_key in ('shield_spell', 'shield'):
            self.shield_bonus = 5
            self.update_derived_stats()
            self.refresh_stats()
            self.log_message("Shield: an invisible barrier snaps into place. +5 AC this round.",
                             color='important')
            self.root.after(8000, self.remove_shield)
            consume_action()
            return True

        if spell_key == 'armor_of_agathys':
            temp = 10 + 5 * upcast
            self.temp_hp = getattr(self, 'temp_hp', 0) + temp
            self.frost_armor = True
            self.log_message(f"Blue-white ice sheathes you: {temp} temporary HP, and anything that "
                             "strikes you takes cold damage.", color='important')
            consume_action()
            return True

        if spell_key == 'shield_of_faith':
            self.faith_bonus = 2
            self.update_derived_stats()
            self.log_message("A shimmering field surrounds you: +2 AC for the rest of the fight.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'bless':
            self.bless_bonus = 2
            self.update_derived_stats()
            self.log_message("A blessing settles over you: +2 to your attack rolls this fight.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'bane':
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -3)
            self.bane_active = True
            self.log_message("A guttering shadow falls on your foes: -3 to their attacks.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'heroism':
            temp = 8 + 4 * upcast
            self.temp_hp = getattr(self, 'temp_hp', 0) + temp
            self.log_message(f"Courage floods through you: {temp} temporary HP and nothing "
                             "frightens you.", color='important')
            consume_action()
            return True

        if spell_key == 'sleep':
            # drops every sufficiently weakened enemy outright (no loot, no XP)
            threshold = 10 * level
            sleepers = [en for en in living() if en['hp'] <= threshold and not en.get('boss')]
            if not sleepers and living() and random.random() < 0.35:
                candidates = [e for e in living() if not e.get('boss')]
                if candidates:
                    sleepers = [min(candidates, key=lambda en: en['hp'])]
            if sleepers:
                for en in sleepers:
                    self.log_message(f"The {en['name']} slumps to the ground, fast asleep!", color='important')
                    self.defeat_enemy(en, reward=False)
            elif living():
                self.log_message("Sleep washes over them and fails to take hold.")
            else:
                self.log_message("You cast Sleep but there's nothing to affect.")
            consume_action()
            return True

        if spell_key == 'charm_person':
            t = self.current_target() if self.in_combat else None
            if t:
                if t.get('boss'):
                    self.log_message(f"The {t['name']} is far too strong-willed for that.",
                                     color='warning')
                elif not enemy_saves(t):
                    t['charmed'] = True
                    self.log_message(f"The {t['name']} lowers its weapon and looks at you fondly.",
                                     color='important')
                    self.draw_combat()
                else:
                    self.log_message(f"The {t['name']} shakes off your charm.")
            consume_action()
            return True

        if spell_key == 'entangle':
            hold_targets(2 + upcast, "Roots burst through the flagstones!")
            consume_action()
            return True

        if spell_key == 'faerie_fire':
            targets = living()
            if targets:
                for en in targets:
                    en['ac'] = max(5, en['ac'] - 2)
                self.log_message("Glittering light outlines every enemy: their AC drops by 2!", color='important')
                self.draw_combat()
            else:
                self.log_message("Motes of glittering light dance around you, finding nothing to outline.")
            consume_action()
            return True

        if spell_key == 'searing_smite':
            self.smite_charge = 2 + upcast
            self.log_message(f"Your weapon glows white-hot: your next hit deals "
                             f"+{2 + upcast}d8.", color='important')
            consume_action()
            return True

        if spell_key == 'hex_spell':
            self.hex_spell_active = True
            self.log_message("A sigil burns itself into the air: +1d6 damage on every hit this fight.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'detect_magic':
            found = 0
            if getattr(self, 'dungeon', None):
                for r in self.dungeon['rooms'].values():
                    if r['type'] in ('mystery', 'chest', 'treasure') and not r['seen']:
                        r['seen'] = True
                        found += 1
                self.draw_dungeon()
            if found:
                self.log_message(f"Magical auras flare on your map: {found} hidden cache"
                                 f"{'s' if found != 1 else ''} revealed!", color='important')
            else:
                self.log_message("You sense no undiscovered magic on this floor.")
            consume_action()
            return True

        if spell_key == 'identify':
            found = 0
            if getattr(self, 'dungeon', None):
                for r in self.dungeon['rooms'].values():
                    if r['type'] == 'trap' and not r['seen']:
                        r['seen'] = True
                        found += 1
                self.draw_dungeon()
            if found:
                self.log_message(f"You recognize the signature of dangerous enchantments: {found} "
                                 f"trap{'s' if found != 1 else ''} marked on your map!", color='important')
            else:
                self.log_message("You detect no unidentified trap magic on this floor.")
            consume_action()
            return True

        # ======================================================= LEVEL 2 ====
        if spell_key == 'scorching_ray':
            rays = 3 + upcast
            targets = living()
            if not targets:
                self.log_message("You gesture for Scorching Ray, but there is no one to hit.")
                consume_action()
                return True
            self.assign_rays(rays, targets, spell_attack, consume_action)
            return True

        if spell_key == 'shatter':
            self.log_message("A sudden ringing note builds until something has to give.")
            damage_all(dice(3 + upcast, 8), 'thunder')
            consume_action()
            return True

        if spell_key == 'moonbeam':
            self.log_message("A shaft of cold silver light stabs down.")
            save_or_damage(dice(2 + upcast, 10), 'radiant')
            linger(2 + upcast, 10, 'radiant', 2, "The moonbeam sweeps across the room")
            consume_action()
            return True

        if spell_key == 'spiritual_weapon':
            self.spirit_weapon = 1 + upcast // 2
            self.log_message("A weightless blade of force takes shape beside you and starts working.",
                             color='important')
            damage_enemy(dice(self.spirit_weapon, 8) + cast_mod, 'force', auto_hit=True)
            consume_action()
            return True

        if spell_key in ('hold_person', 'hold_monster'):
            t = self.current_target() if self.in_combat else None
            if t:
                too_big = t.get('boss') and spell_key == 'hold_person'
                if too_big:
                    self.log_message(f"Hold Person cannot get a grip on something like the "
                                     f"{t['name']}. You would need Hold Monster.", color='warning')
                elif not enemy_saves(t):
                    t['held'] = True
                    self.log_message(f"You hold the {t['name']} rigid (failed save vs DC {spell_dc})! "
                                     "It will miss its next turn.", color='important')
                    self.draw_combat()
                else:
                    self.log_message(f"The {t['name']} resists (save vs DC {spell_dc}).")
            consume_action()
            return True

        if spell_key == 'silence':
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -2)
            self.log_message("A bubble of absolute quiet drops over the room: -2 to enemy attacks.",
                             color='important')
            consume_action()
            return True

        if spell_key in ('misty_step', 'dimension_door', 'teleport'):
            self.escape_ready = True
            where = ("You blink through space to a safer position."
                     if spell_key == 'misty_step' else
                     "You tear a doorway in the air and hold it open.")
            self.log_message(f"{where} Your next attempt to Flee will succeed automatically.",
                             color='important')
            consume_action()
            return True

        if spell_key in ('blur', 'mirror_image', 'invisibility', 'greater_invisibility'):
            penalty = {'blur': 2, 'mirror_image': 3, 'invisibility': 4,
                       'greater_invisibility': 6}[spell_key]
            if spell_key == 'invisibility':
                penalty += upcast
            flavor = {'blur': "Your outline wavers and shifts",
                      'mirror_image': "Illusory duplicates of you flicker into being",
                      'invisibility': "You fade from sight",
                      'greater_invisibility': "You vanish utterly, even as you strike"}[spell_key]
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -penalty)
            if spell_key == 'greater_invisibility':
                self.greater_invis = True
            self.log_message(f"{flavor}: enemies attack at -{penalty}.", color='important')
            consume_action()
            return True

        if spell_key in ('levitate', 'fly'):
            self.levitate_charge = True
            self.log_message("You rise gently off the ground \u2014 your next blocked step in the "
                             "dungeon will pass right over the wall!", color='important')
            consume_action()
            return True

        if spell_key == 'gust_of_wind':
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -2)
            self.log_message("A roaring wind staggers your foes: -2 to their attacks this round.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'mage_armor':
            self.mage_armor_active = True
            self.update_derived_stats()
            self.log_message("A film of force settles over you: AC 13 + DEX while you "
                             "wear no armor. It holds until your next long rest.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'barkskin':
            self.barkskin_dr = 3
            self.update_derived_stats()
            self.log_message("Your skin roughens into bark: 3 damage reduction this fight.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'enhance_ability':
            self.check_bonus_temp = 4
            self.log_message("Strength and surety flow into you: +4 on ability checks.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'lesser_restoration':
            if getattr(self, 'poisoned', 0) or getattr(self, 'cursed_rounds', 0):
                self.poisoned = 0
                self.cursed_rounds = 0
                self.log_message("Whatever was in you goes out of you.", color='important')
            else:
                self.log_message("You feel briefly, thoroughly well. There was nothing to cure.")
            consume_action()
            return True

        if spell_key == 'aid':
            bump = 5 + 5 * upcast
            self.aid_bonus = getattr(self, 'aid_bonus', 0) + bump
            self.update_derived_stats()
            self.health = min(self.max_health, self.health + bump)
            self.log_message(f"You feel hardier: +{bump} maximum and current HP.", color='important')
            consume_action()
            return True

        # ======================================================= LEVEL 3 ====
        if spell_key == 'fireball':
            self.log_message("A tiny bead streaks out and detonates in a roaring blast!")
            damage_all(dice(8 + upcast, 6), 'fire')
            consume_action()
            return True

        if spell_key == 'lightning_bolt':
            self.log_message("A bolt of lightning tears through the enemy line!")
            damage_all(dice(8 + upcast, 6), 'lightning')
            consume_action()
            return True

        if spell_key == 'call_lightning':
            self.log_message("Storm clouds gather where no sky should be.")
            damage_all(dice(3 + upcast, 10), 'lightning')
            linger(3 + upcast, 10, 'lightning', 2, "Another bolt cracks down from your storm")
            consume_action()
            return True

        if spell_key == 'spirit_guardians':
            self.log_message("Spectral shapes wheel around you, striking anything that comes close.")
            damage_all(dice(3 + upcast, 8), 'radiant')
            self.enemy_attack_penalty = min(self.enemy_attack_penalty, -2)
            linger(3 + upcast, 8, 'radiant', 2, "Your guardians wheel around again")
            consume_action()
            return True

        if spell_key == 'sleet_storm':
            targets = living()
            for en in targets:
                en['held'] = True
            if targets:
                self.log_message("The floor turns to sheet ice and everything goes down hard. "
                                 "No saving throw.", color='important')
                self.draw_combat()
            else:
                self.log_message("Freezing rain falls on an empty room.")
            consume_action()
            return True

        if spell_key == 'stinking_cloud':
            hold_targets(len(living()), "A putrid cloud erupts!")
            consume_action()
            return True

        if spell_key == 'hypnotic_pattern':
            hold_targets(2 + upcast, "Impossible colours twist through the air.")
            consume_action()
            return True

        if spell_key == 'fear':
            threshold = 14 * level
            routed = [en for en in living() if en['hp'] <= threshold and not en.get('boss')]
            if routed:
                for en in routed:
                    self.log_message(f"The {en['name']} throws down its weapon and runs.",
                                     color='important')
                    self.defeat_enemy(en, reward=False)
            else:
                self.enemy_attack_penalty = min(self.enemy_attack_penalty, -3)
                self.log_message("Nothing breaks, but everything hesitates: -3 to their attacks.",
                                 color='important')
            consume_action()
            return True

        if spell_key == 'haste':
            self.start_haste(rounds=3 + upcast)
            consume_action()
            return True

        if spell_key == 'counterspell':
            # nothing here casts spells at you, so never waste the slot
            refund()
            self.log_message("You hold Counterspell ready, but nothing is casting at you.")
            return False

        if spell_key == 'beacon_of_hope':
            self.beacon_of_hope = True
            self.log_message("Hope kindles: every heal you receive is doubled for this fight.",
                             color='important')
            consume_action()
            return True

        if spell_key in ('revivify', 'death_ward'):
            self.death_ward = True
            self.log_message("A ward settles over your heart. The next blow that would kill you "
                             "will leave you at 1 HP instead.", color='important')
            consume_action()
            return True

        if spell_key == 'guardian_of_faith':
            linger(2 + upcast, 8, 'radiant', 3, "Your spectral warden strikes")
            self.log_message("A faceless warden in gleaming armour takes up position beside you.",
                             color='important')
            consume_action()
            return True

        if spell_key == 'guardian_of_flame':
            linger(2 + upcast, 6, 'fire', 3, "Your fire elemental lashes out")
            self.log_message("A knot of flame unfolds into something roughly person-shaped, "
                             "and it is on your side.", color='important')
            consume_action()
            return True

        if spell_key == 'conjure_barrage':
            self.log_message("You fling a weapon forward and it becomes a hundred of them.")
            damage_all(dice(4 + upcast, 8), 'piercing')
            consume_action()
            return True

        if spell_key == 'arcane_eye':
            if getattr(self, 'dungeon', None):
                for r in self.dungeon['rooms'].values():
                    r['seen'] = True
                self.draw_dungeon()
                self.log_message("An invisible eye drifts away and shows you the entire floor.",
                                 color='important')
            else:
                self.log_message("Your arcane eye drifts around a room you have already seen.")
            consume_action()
            return True

        # ======================================================= LEVEL 4 ====
        if spell_key == 'ice_storm':
            self.log_message("Jagged hail the size of fists comes down through the ceiling.")
            damage_all(dice(4, 6), 'bludgeoning')
            damage_all(dice(4 + upcast, 6), 'cold')
            consume_action()
            return True

        if spell_key == 'wall_of_fire':
            self.log_message("A sheet of roaring flame rises out of the floor.")
            damage_all(dice(5 + upcast, 8), 'fire')
            linger(4, 8, 'fire', 2, "Your wall of fire roars again")
            consume_action()
            return True

        if spell_key == 'blight':
            self.log_message("You close your fist and something inside your target dries out.")
            save_or_damage(dice(8 + upcast, 8), 'necrotic')
            consume_action()
            return True

        if spell_key == 'polymorph':
            t = self.current_target() if self.in_combat else None
            if t:
                if t.get('boss') and upcast < 2:
                    self.log_message(f"The {t['name']} is too much to reshape with a slot this "
                                     "small. Try again from higher up.", color='warning')
                elif not enemy_saves(t):
                    self.log_message(f"The {t['name']} shrinks, bleats once, and hops away as a "
                                     "sheep.", color='important')
                    self.defeat_enemy(t, reward=False)
                else:
                    self.log_message(f"The {t['name']} resists the change.")
            consume_action()
            return True

        if spell_key == 'confusion':
            targets = [e for e in living() if not enemy_saves(e)][:2 + upcast]
            if targets:
                for en in targets:
                    en['held'] = True
                    other = [o for o in living() if o is not en]
                    if other:
                        victim = random.choice(other)
                        hurt = dice(2, 8)
                        self.log_message(f"The {en['name']} rounds on the {victim['name']} instead!",
                                         color='important')
                        self.hit_enemy(victim, hurt, 'confusion')
                self.draw_combat()
            else:
                self.log_message("The room wobbles, and everything keeps its head.")
            consume_action()
            return True

        if spell_key == 'banishment':
            t = self.current_target() if self.in_combat else None
            if t:
                if t.get('boss') and upcast < 1:
                    self.log_message(f"The {t['name']} is anchored here too firmly for a "
                                     "level 4 slot.", color='warning')
                elif not enemy_saves(t):
                    self.log_message(f"The {t['name']} is folded out of the room entirely. "
                                     "It does not come back.", color='important')
                    self.defeat_enemy(t, reward=False)
                else:
                    self.log_message(f"The {t['name']} holds on to this plane.")
            consume_action()
            return True

        # ======================================================= LEVEL 5 ====
        if spell_key == 'cone_of_cold':
            self.log_message("A wide arc of killing cold sweeps out from your hands.")
            damage_all(dice(8 + upcast, 8), 'cold')
            consume_action()
            return True

        if spell_key == 'flame_strike':
            self.log_message("A column of fire and holy light comes down through the roof.")
            damage_all(dice(4 + upcast, 6), 'fire')
            damage_all(dice(4 + upcast, 6), 'radiant')
            consume_action()
            return True

        if spell_key == 'chain_lightning':
            targets = living()
            if not targets:
                self.log_message("Lightning gathers on your fingertips with nowhere to go.")
                consume_action()
                return True
            primary = self.current_target()
            main = dice(10 + upcast, 8)
            self.log_message("Lightning leaps from your hand and goes looking for the rest of them.")
            if primary:
                self.hit_enemy(primary, main, 'lightning')
            for en in list(living()):
                if en is primary:
                    continue
                self.hit_enemy(en, max(1, main // 2), 'lightning')
            consume_action()
            return True

        if spell_key == 'destructive_wave':
            self.log_message("You strike the ground and the room answers.")
            damage_all(dice(5 + upcast, 6), 'thunder')
            damage_all(dice(5 + upcast, 6), 'radiant')
            for en in living():
                en['held'] = True
            self.draw_combat()
            consume_action()
            return True

        if spell_key == 'dominate_person':
            t = self.current_target() if self.in_combat else None
            if t:
                if t.get('boss') and upcast < 1:
                    self.log_message(f"The {t['name']}'s mind is a locked door.", color='warning')
                elif not enemy_saves(t):
                    t['dominated'] = 2
                    self.log_message(f"The {t['name']} straightens, turns, and picks a new enemy.",
                                     color='important')
                    self.draw_combat()
                else:
                    self.log_message(f"The {t['name']} shakes you out of its head.")
            consume_action()
            return True

        if spell_key == 'insect_plague':
            self.log_message("The air thickens, then starts biting.")
            damage_all(dice(5 + upcast, 10), 'piercing')
            linger(3, 10, 'piercing', 3, "The swarm is still feeding")
            consume_action()
            return True

        if spell_key == 'mass_cure_wounds':
            heal(dice(5 + upcast, 8) + cast_mod, "Healing light rolls out from you")
            consume_action()
            return True

        if spell_key == 'wall_of_force':
            self.wall_of_force = True
            self.log_message("An invisible slab of pure force seals you off. Nothing reaches you "
                             "this round.", color='important')
            consume_action()
            return True

        if spell_key == 'telekinesis':
            t = self.current_target() if self.in_combat else None
            self.log_message("You close your hand and something very heavy leaves the floor.")
            if t:
                self.hit_enemy(t, dice(6 + upcast, 8), 'bludgeoning')
                if t['hp'] > 0:
                    t['held'] = True
                    self.log_message(f"The {t['name']} hits the wall and stays down a moment.",
                                     color='important')
                    self.draw_combat()
            consume_action()
            return True

        if spell_key == 'swift_quiver':
            self.extra_shots = 2
            self.log_message("Your quiver refills as fast as you can empty it: two extra shots "
                             "with every attack this fight.", color='important')
            consume_action()
            return True

        if spell_key == 'soul_harvest':
            total = dice(6 + upcast, 10)
            self.log_message("You reach out and take something that was never yours.")
            drained = 0
            for en in list(living()):
                before = en['hp']
                self.hit_enemy(en, total, 'necrotic')
                drained += before - en['hp']
            if drained:
                heal(drained // 2, "The stolen life pours into you")
            consume_action()
            return True

        # Any spell without its own branch above lands here and just does some
        # damage. If a new spell 'works but does nothing special', it is because
        # it reached this point - go back and give it a branch.
        if living():
            dmg = dice(max(1, level) + upcast, 6)
            self.log_message(f"You unleash {name or spell_key}.")
            damage_enemy(dmg, 'arcane')
            consume_action()
            return True

        # Nothing to affect: refund the slot we deducted above so it isn't wasted
        refund()
        self.log_message("You try to cast, but nothing happens.")
        return False

    def assign_rays(self, rays, targets, spell_attack, consume_action):
        """Let the player split Scorching Ray's rays between the enemies on screen."""
        win = self.make_popup("Scorching Ray - assign targets")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text=f"Allocate {rays} rays among targets:",
                  font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        variables = {}
        total_var = tk.StringVar(value=f"0 of {rays} assigned")

        def update_total(*_):
            total_var.set(f"{sum(v.get() for v in variables.values())} of {rays} assigned")

        for en in targets:
            row = ttk.Frame(frm)
            row.pack(fill=tk.X, pady=(2, 2))
            ttk.Label(row, text=f"{en['name']}  ({en['hp']}/{en['max_hp']} HP)").pack(side=tk.LEFT)
            var = tk.IntVar(value=0)
            ttk.Spinbox(row, from_=0, to=rays, width=3, textvariable=var).pack(side=tk.RIGHT)
            variables[id(en)] = var
            var.trace_add('write', update_total)

        ttk.Label(frm, textvariable=total_var, style='Dim.TLabel').pack(anchor=tk.W, pady=(6, 4))

        def confirm():
            allocated = sum(v.get() for v in variables.values())
            if allocated > rays:
                messagebox.showerror("Too many rays",
                                     f"You assigned {allocated} rays but only have {rays}.")
                return
            if allocated == 0:
                # nothing assigned: spread them over whatever is still standing
                for i in range(rays):
                    if targets:
                        variables[id(targets[i % len(targets)])].set(
                            variables[id(targets[i % len(targets)])].get() + 1)
            for en in targets:
                for _ in range(variables[id(en)].get()):
                    if en['hp'] <= 0:
                        break
                    if spell_attack(en):
                        self.hit_enemy(en, random.randint(1, 6) + random.randint(1, 6), 'fire')
            win.destroy()
            consume_action()

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btns, text="Confirm", command=confirm).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Spread Evenly",
                   command=lambda: (win.destroy(), self._spread_rays(rays, targets,
                                                                    spell_attack, consume_action))
                   ).pack(side=tk.RIGHT, padx=(6, 0))
        self.place_window(win, min_w=380, min_h=240)
        win.wait_window()

    def _spread_rays(self, rays, targets, spell_attack, consume_action):
        """Fire Scorching Ray's rays round-robin at everything still standing."""
        for i in range(rays):
            alive = [e for e in targets if e['hp'] > 0]
            if not alive:
                break
            en = alive[i % len(alive)]
            if spell_attack(en):
                self.hit_enemy(en, random.randint(1, 6) + random.randint(1, 6), 'fire')
        consume_action()

    # ------------------------------------------------------------ spellbook

    def open_spellbook(self):
        """The spellbook: everything you know, grouped by level, with upcast buttons.

        Each leveled spell gets one button per slot level you could spend on it, so
        casting Fireball from a level 5 slot is a single click. Spells you cannot
        cast right now are greyed out with the reason why, and the rest of your class
        list is listed underneath so progression is visible.
        
"""
        if not self.class_spell_list():
            self.log_message(f"A {getattr(self, 'char_class', 'character')} has no spells to cast.")
            return
        self.open_sheet('spells')

    def _build_spellbook_tab(self, container):
        """Build the spellbook into its tab of the shared character window."""
        outer = container
        if not self.class_spell_list():
            ttk.Label(outer, text=f"A {getattr(self, 'char_class', None) or 'character'} "
                                  "has no spells to cast.",
                      style='Dim.TLabel').pack(anchor=tk.W, pady=8)
            return

        slots = getattr(self, 'spell_slots_by_level', {})
        maxs = getattr(self, 'spell_slots_max_by_level', {})
        slot_line = "   ".join(f"L{lvl}: {slots.get(lvl, 0)}/{maxs.get(lvl, 0)}"
                               for lvl in SPELL_LEVELS if maxs.get(lvl, 0))
        ttk.Label(outer, text=f"{self.char_class} spells \u2014 slots  {slot_line or '(none)'}",
                  font=("Segoe UI", 11, "bold"), style='Gold.TLabel').pack(anchor=tk.W)
        ttk.Label(outer, text="Cantrips are free and get stronger as you level. Leveled spells show "
                              "one button per slot you could spend \u2014 a bigger slot casts a "
                              "bigger spell.",
                  style='Dim.TLabel', wraplength=620, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 2))
        if not self.in_combat:
            ttk.Label(outer, text="Out of combat you can only cast utility and healing spells.",
                      style='Dim.TLabel').pack(anchor=tk.W, pady=(0, 4))

        frame = self.make_scrollable(outer)

        def try_cast(key, lvl):
            ok, reason = self.can_cast_now(key, lvl)
            if not ok:
                self.log_message(reason)
                return
            if self.cast_spell(key, level=lvl):
                self.close_sheet()
                self.refresh_stats()
                self.refresh_buttons()
                self.prompt_end_of_turn()

        known = [k for k in self.known_spells if k in self.spell_catalog]
        ttk.Label(frame, text="Known Spells", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(4, 0))
        if not known:
            ttk.Label(frame, text="(no known spells)").pack(anchor=tk.W, pady=(4, 4))

        for lvl in (0,) + tuple(SPELL_LEVELS):
            at_level = [k for k in known if self.spell_catalog[k][2] == lvl]
            if not at_level:
                continue
            box = ttk.LabelFrame(
                frame, text="Cantrips \u2014 free, unlimited" if lvl == 0 else f"Level {lvl}",
                padding=6)
            box.pack(fill=tk.X, pady=(6, 2))
            for key in at_level:
                name, desc, _lvl, action = self.spell_catalog[key]
                row = ttk.Frame(box)
                row.pack(fill=tk.X, pady=(4, 2))
                ttk.Label(row, text=f"{name}  [{action}]", font=("Segoe UI", 10, "bold"),
                          style='Gold.TLabel').pack(anchor=tk.W)
                ttk.Label(row, text=desc, style='Dim.TLabel', wraplength=560,
                          justify=tk.LEFT).pack(anchor=tk.W)
                note = SPELL_UPCAST.get(key)
                if note and lvl > 0:
                    ttk.Label(row, text=f"Upcast: {note}", style='Dim.TLabel').pack(anchor=tk.W)
                btn_row = ttk.Frame(row)
                btn_row.pack(anchor=tk.W, pady=(2, 0))
                usable = self.castable_slot_levels(key)
                if lvl == 0:
                    ok, reason = self.can_cast_now(key, 0)
                    b = ttk.Button(btn_row, text="Cast", command=lambda k=key: try_cast(k, 0))
                    b.pack(side=tk.LEFT, padx=(0, 6))
                    if not ok:
                        b.state(['disabled'])
                        ttk.Label(btn_row, text=reason, style='Dim.TLabel').pack(side=tk.LEFT)
                elif not usable:
                    ok, reason = self.can_cast_now(key, lvl)
                    ttk.Label(btn_row, text=reason or "No slots available.",
                              style='Dim.TLabel').pack(side=tk.LEFT)
                else:
                    for slot_lvl in usable:
                        label = f"Cast (L{slot_lvl})" if slot_lvl == lvl else f"Upcast L{slot_lvl}"
                        ttk.Button(btn_row, text=label,
                                   command=lambda k=key, l=slot_lvl: try_cast(k, l)
                                   ).pack(side=tk.LEFT, padx=(0, 6))

        # the rest of this class's list, so you can see what's still to come
        rest = [k for k in self.class_spell_list() if k not in known]
        if rest:
            box = ttk.LabelFrame(frame, text="Not yet learned", padding=6)
            box.pack(fill=tk.X, pady=(10, 4))
            top = self.max_spell_level()
            for key in sorted(rest, key=lambda k: (self.spell_catalog[k][2], k)):
                name, desc, lvl, action = self.spell_catalog[key]
                note = "" if lvl <= top else "  (too high a level for you yet)"
                ttk.Label(box, text=f"\u2022 {name} ({'Cantrip' if lvl == 0 else 'Level ' + str(lvl)}) "
                                    f"\u2014 {desc}{note}", style='Dim.TLabel',
                          wraplength=580, justify=tk.LEFT).pack(anchor=tk.W)


    def remove_shield(self):
        """Drop the Shield spell's AC bonus when it expires."""
        if hasattr(self, 'shield_bonus'):
            try:
                del self.shield_bonus
            except Exception:
                pass
            self.log_message("Your magical shield fades.")
        self.update_derived_stats()
        self.refresh_stats()

    def open_wizard_menu(self):
        """Small menu shown to casters from the Class Ability button."""
        menu = self.make_popup(f"{getattr(self, 'char_class', 'Caster')} Spells")
        frame = ttk.Frame(menu, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        slots = getattr(self, 'spell_slots_by_level', {})
        maxs = getattr(self, 'spell_slots_max_by_level', {})
        line = "   ".join(f"L{lvl}: {slots.get(lvl, 0)}/{maxs.get(lvl, 0)}"
                          for lvl in SPELL_LEVELS if maxs.get(lvl, 0))
        ttk.Label(frame, text=f"Spell Slots \u2014 {line or 'none'}").pack(anchor=tk.W)
        ttk.Button(frame, text="Open Spellbook",
                   command=lambda: [menu.destroy(), self.open_spellbook()]).pack(fill=tk.X, pady=(8, 8))
        ttk.Button(frame, text="Close", command=menu.destroy).pack(pady=(8, 0))
        self.place_window(menu, min_w=360, min_h=200)
