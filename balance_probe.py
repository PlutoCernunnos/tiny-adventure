"""Balance probe: play real fights through the game's own combat code.

For several classes and seeds, walk floors 1..12: a handful of trash packs per
floor (made by make_enemy_pack), a boss on every BOSS_EVERY floor (make_boss),
short rests between fights (with the real 35% ambush risk), a long rest and a
potion top-up between floors. Reports, per floor: average rounds per fight,
damage taken per fight, deaths, and stalled fights (hit the 40-round cap).
"""
import importlib.util, random, statistics, sys
import tkinter as tk

spec = importlib.util.spec_from_file_location("game", "mane_game.py")
game = importlib.util.module_from_spec(spec); spec.loader.exec_module(game)

T = game.TinyAdventureGUI
T.init_sounds = lambda self: None
T.show_dice_roll = lambda *a, **k: None
T.open_main_menu = lambda self: None
T.open_spell_learning = lambda self, *a, **k: None
T.open_asi_dialog = lambda self, *a, **k: None
T.assign_rays = lambda self, *a, **k: self._spread_rays(*a, **k)

root = tk.Tk()
G = T.__new__(T); G.__init__(root)
G.sound_enabled = False; G.music_enabled = False; G.log_delay_ms = 0
# the probe measures the RAW dials in data.py, so the adaptive dial (which
# would quietly re-tune packs mid-run) is pinned off here
G.adaptive_enabled = False
# display-only work, stubbed for speed
for name in ('draw_combat', 'refresh_stats', 'refresh_inventory', 'refresh_buttons',
             'float_text', 'flash_card', 'play_sound', 'log_message',
             'hide_combat_panel', 'show_combat_panel', 'prompt_end_of_turn'):
    setattr(G, name, lambda *a, **k: None)

DEATHS = {'n': 0}
def fake_death(self=None):
    DEATHS['n'] += 1
    G.in_combat = False; G.enemy_attack_pending = False
    G.enemies = []; G.pending_enemies = []; G.current_event = None
    G._enemy_queue = []
    G.clear_combat_effects(); G.update_derived_stats()
    G.health = G.max_health
G.handle_death = fake_death

DMG_SPELLS = ['fireball', 'lightning_bolt', 'scorching_ray', 'shield_bolt',
              'shatter', 'burning_hands', 'thunderwave', 'magic_missile',
              'eldritch_blast', 'sacred_flame', 'fire_bolt', 'ray_of_frost',
              'thorn_whip', 'toll_the_dead', 'vicious_mockery']

def slot_for(lvl):
    for s in range(max(1, lvl), 6):
        if G.spell_slots_by_level.get(s, 0) > 0:
            return s
    return None

def try_spell():
    big_fight = len(G.living_enemies()) >= 2 or any(e.get('boss') for e in G.living_enemies())
    for key in DMG_SPELLS:
        if key not in G.known_spells or key not in G.spell_catalog:
            continue
        lvl = G.spell_catalog[key][2]
        if lvl == 0:
            if G.cast_spell(key, level=0):
                return True
        elif big_fight:   # save the real slots for packs and bosses
            s = slot_for(lvl)
            if s and G.cast_spell(key, level=s):
                return True
    return False

def try_heal_spell():
    if 'cure_wounds' in G.known_spells:
        s = slot_for(1)
        if s and G.cast_spell('cure_wounds', level=min(s, 2)):
            return True
    return False

def second_wind():
    if G.char_class == 'Fighter' and G.second_wind_available and G.player_bonus_available:
        G.second_wind_available = False
        G.player_bonus_available = False
        G.heal_player(random.randint(1, 10) + G.player_level, 'Second Wind')
        return True
    return False

def pick_target():
    # focus down the weakest minion first; face the boss once the room is clear
    alive = G.living_enemies()
    if not alive:
        return None
    minions = [e for e in alive if not e.get('boss')]
    pool = minions or alive
    tgt = min(pool, key=lambda e: e['hp'])
    G.target_index = G.enemies.index(tgt)
    return tgt

def prep_buffs():
    # a caster walks the halls with their armor spell up; the game already has
    # these, the probe was just too lazy to cast them
    for key in ('mage_armor', 'barkskin', 'shield_of_faith'):
        if key in G.known_spells:
            G.cast_spell(key, level=max(1, G.spell_catalog[key][2]))
            break

def player_turn():
    # a cleric opens a hard fight with its floating blade (bonus action)
    if ('spiritual_weapon' in G.known_spells and not getattr(G, 'spirit_weapon', 0)
            and G.player_bonus_available
            and (any(e.get('boss') for e in G.living_enemies()) or len(G.living_enemies()) >= 2)):
        s = slot_for(2)
        if s:
            G.cast_spell('spiritual_weapon', level=s)
    if (G.char_class == 'Rogue' and G.sneak_available and not G.sneak_active
            and G.player_bonus_available):
        G.sneak_active = True            # prepare Sneak Attack (bonus action)
        G.player_bonus_available = False
    low = G.health < 0.55 * G.max_health
    if low and not second_wind():
        if 'potion' in G.inventory and G.player_bonus_available:
            G.bonus_potion()
    t = pick_target()
    if t is None or not G.in_combat:
        return
    # cure is the emergency backup, not the plan: potions are the bonus-action
    # heal, and the action keeps swinging unless things are truly dire
    if (G.player_action_available and G.health < 0.3 * G.max_health
            and 'potion' not in G.inventory and try_heal_spell()):
        pass
    elif G.player_action_available:
        if not (G.known_spells and try_spell()):
            # heavy when it still hits >=50% of the time, else quick
            p_heavy = (21 - (t['ac'] - (G.player_attack_bonus - 2))) / 20
            (G.do_heavy_attack if p_heavy >= 0.5 else G.do_quick_attack)()
    if G.in_combat and G.player_bonus_available:
        if G.health < 0.5 * G.max_health:
            G.bonus_defend()          # raise the shield when it is getting scary
        elif pick_target() is not None:
            G.bonus_offhand_strike()

def run_fight(pack, stats_row):
    G.pending_enemies = pack
    G.current_event = 'enemy'
    hp_before, deaths_before = G.health, DEATHS['n']
    healed = {'n': 0}
    real_heal = G.heal_player
    G.heal_player = lambda amt, reason='': healed.__setitem__('n', healed['n'] + real_heal(amt, reason))
    G.do_attack()
    rounds = 0
    while G.in_combat and rounds < 40:
        rounds += 1
        player_turn()
        if not G.in_combat:
            break
        G.end_turn()
        guard = 0
        while getattr(G, '_enemy_queue', None) and guard < 40:
            G._enemy_turn_step(); guard += 1
        if G.in_combat:
            G._enemy_turn_step()
    G.heal_player = real_heal
    stalled = G.in_combat and rounds >= 40
    if stalled:
        fake_death()          # count an unwinnable slog as a loss
    died = DEATHS['n'] > deaths_before
    taken = (hp_before - G.health) + healed['n'] if not died else hp_before + healed['n']
    G._clear_post_victory()
    stats_row['fights'] += 1
    stats_row['rounds'].append(rounds)
    stats_row['taken'].append(max(0, taken))
    stats_row['deaths'] += 1 if died else 0
    stats_row['stalls'] += 1 if stalled else 0

def short_rest():
    if G.hit_dice <= 0:
        return None
    G.hit_dice -= 1; G.temp_hp = 0
    G.heal_player(max(1, random.randint(1, G.class_hit_die) + G.ability_mod('constitution')), 'rest')
    if random.random() < 0.35:
        return 'ambush'
    return 'ok'

def long_rest():
    G.health = G.max_health
    G.hit_dice = G.hit_dice_max
    G.spell_slots_by_level = dict(G.spell_slots_max_by_level)
    G.class_resource_available = True
    G.second_wind_available = True; G.action_surge_available = True
    G.sneak_available = (G.char_class == 'Rogue')
    G.poisoned = 0; G.temp_hp = 0

def catch_up():
    while getattr(G, 'asi_pending', 0):
        G.asi_pending -= 1
        prio = (game.CLASS_STAT_PRIORITY.get(G.char_class) or ['strength'])[0]
        setattr(G, prio, min(game.ABILITY_CAP, getattr(G, prio) + 2))
    if G.caster_type:
        G.known_spells = G.auto_pick_spells(G.char_class, G.player_level)
    G.update_derived_stats()

CLASSES = ['Fighter', 'Rogue', 'Wizard', 'Cleric']
SEEDS = range(10)
FLOORS = 12
agg = {}   # (cls, floor, kind) -> row

for cls in CLASSES:
    for seed in SEEDS:
        random.seed(1000 + seed)
        G.quick_start_class(cls, level=1)
        G.difficulty = 'Normal'
        for floor in range(1, FLOORS + 1):
            for kind in ('trash', 'boss'):
                agg.setdefault((cls, floor, kind),
                               {'fights': 0, 'rounds': [], 'taken': [], 'deaths': 0,
                                'stalls': 0, 'levels': []})
            agg[(cls, floor, 'trash')]['levels'].append(G.player_level)
            fights = 4 + random.randint(0, 2)
            prep_buffs()
            for _ in range(fights):
                run_fight(G.make_enemy_pack(floor), agg[(cls, floor, 'trash')])
                catch_up()
                while G.health < 0.6 * G.max_health:
                    r = short_rest()
                    if r is None:
                        break
                    if r == 'ambush':
                        run_fight(G.make_enemy_pack(floor), agg[(cls, floor, 'trash')])
            if floor % game.BOSS_EVERY == 0:
                long_rest()   # everyone camps before the boss door
                run_fight(G.make_boss(floor), agg[(cls, floor, 'boss')])
                catch_up()
            # between floors: camp (usually) and shop for potions
            if random.random() < 0.75:
                long_rest()
            while G.inventory.count('potion') < 6 and G.gold >= 7:
                G.gold -= 7; G.inventory.append('potion')

print(f"{'class':8} {'fl':>2} {'lvl':>4} | trash: {'n':>3} {'rnds':>5} {'dmg/f':>6} {'die':>3} {'stall':>5} | boss: {'rnds':>5} {'dmg':>5} {'die':>3} {'stall':>5}")
for cls in CLASSES:
    for floor in range(1, FLOORS + 1):
        t = agg[(cls, floor, 'trash')]
        b = agg[(cls, floor, 'boss')]
        lvl = statistics.mean(t['levels']) if t['levels'] else 0
        def fmt(row):
            if not row['fights']:
                return f"{'-':>5} {'-':>5} {'-':>3} {'-':>5}"
            return (f"{statistics.mean(row['rounds']):5.1f} {statistics.mean(row['taken']):5.1f} "
                    f"{row['deaths']:3d} {row['stalls']:5d}")
        print(f"{cls:8} {floor:2d} {lvl:4.1f} | {t['fights']:9d} {fmt(t)} | {fmt(b):>10}")
    print()
print(f"total deaths: {DEATHS['n']}")
root.destroy()
