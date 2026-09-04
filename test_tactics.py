"""Headless checks for tactics (range/cover/moves), enemy AI, companions and
adaptive difficulty. Run under xvfb-run, like the other suites."""
import os, sys, random, importlib.util, tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "game", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mane_game.py"))
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)

fails = []
def check(label, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + label + (("   " + str(extra)) if extra else ""))
    if not cond:
        fails.append(label)

root = tk.Tk()
game.TinyAdventureGUI.init_sounds = lambda self: None
G = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI)
G.__init__(root)
G.sound_enabled = False
G.music_enabled = False
G.log_delay_ms = 0
G.show_dice_roll = lambda *a, **k: None
G.assign_rays = lambda *a, **k: G._spread_rays(*a, **k)

logs = []
_orig_log = G.log_message
def capture_log(msg, *a, **k):
    logs.append(str(msg))
    _orig_log(msg, *a, **k)
G.log_message = capture_log

def fresh_fight(enemies, obstacle=None):
    """Reset combat state and start a fight with exactly these enemies."""
    G.in_combat = False
    G.enemy_attack_pending = False
    G.enemies = []
    G.health = G.max_health
    G.pending_enemies = enemies
    G.current_event = 'enemy'
    logs.clear()
    G.do_attack()
    G.obstacle = obstacle  # deterministic for the test
    return G.enemies

def pump_enemies():
    guard = 0
    while getattr(G, '_enemy_queue', None) and guard < 12:
        G._enemy_turn_step(); guard += 1
    G._enemy_turn_step()  # empty queue -> start_of_round


# ---------------------------------------------------------------- setup
G.quick_start_class('Fighter', level=3)
check("fighter quick start", G.char_class == 'Fighter')

# =================== 1. Range: melee auto-closes on a far target ===========
es = fresh_fight(G.make_enemy_pack(1, count=2))
es[0].update(dist='far', ranged=True)
G.target_index = 0
check("fight starts with the free move", G.player_move_available)
G.do_quick_attack()
check("melee attack on a far target closes the distance", es[0]['dist'] == 'near')
check("closing consumed the free move", not G.player_move_available)
check("the attack still spent the action (economy unchanged)", not G.player_action_available)
check("enemies did not counterattack automatically", not G.enemy_attack_pending)

# =================== 2. Overextended lunge when the move is spent ==========
es = fresh_fight(G.make_enemy_pack(1, count=1))
es[0].update(dist='far', ranged=True)
G.player_move_available = False
logs.clear()
G.do_quick_attack()
check("no move left: the target stays at range", es[0]['dist'] == 'far')
check("...and the lunge penalty is announced", any('lunge' in m for m in logs))

# =================== 3. Fall Back: swipes for a Fighter, free for a Rogue ==
es = fresh_fight(G.make_enemy_pack(1, count=2))
for e in es:
    e.update(dist='near', ranged=False, atk=-30)   # swipes always miss
hp_before = G.health
G.do_fall_back()
check("fall back pushes everything to range", all(e['dist'] == 'far' for e in G.living_enemies()))
check("fall back spends the move", not G.player_move_available)
check("missed parting swipes leave you unhurt", G.health == hp_before)

G.quick_start_class('Rogue', level=3)
es = fresh_fight(G.make_enemy_pack(1, count=2))
for e in es:
    e.update(dist='near', ranged=False, atk=30)    # would ALWAYS hit if rolled
hp_before = G.health
G.do_fall_back()
check("rogue cunning footwork: no parting swipes at all", G.health == hp_before)
check("rogue fall back still moves everything to range",
      all(e['dist'] == 'far' for e in G.living_enemies()))

# =================== 4. Take Cover and the AC it grants ====================
G.quick_start_class('Fighter', level=3)
es = fresh_fight(G.make_enemy_pack(1, count=1), obstacle=('a toppled pillar', 'x'))
G.do_take_cover()
check("take cover sets the flag", G.player_in_cover)
check("take cover spends the move", not G.player_move_available)

# a shot that hits your bare AC but not AC+cover must miss
e = es[0]
e.update(ranged=True, dist='far', atk=0)
need = G.player_ac  # forced d20 roll: hits AC exactly, misses AC + COVER_AC
_orig_randint = random.randint
random.randint = lambda a, b: need
hp_before = G.health
alive = G.enemy_single_attack(e)
random.randint = _orig_randint
check("cover turns a hit into a miss against ranged", G.health == hp_before and alive)
check("the blocked shot is credited to the cover", any('thuds into' in m for m in logs[-3:]))

# melee ignores your cover entirely
e.update(ranged=False, dist='near')
random.randint = lambda a, b: need if b == 20 else 1
hp_before = G.health
G.enemy_single_attack(e)
random.randint = _orig_randint
check("melee walks around the barricade (cover ignored)", G.health < hp_before)

# =================== 5. Your shots vs an enemy in cover ====================
es = fresh_fight(G.make_enemy_pack(1, count=1), obstacle=('a heap of rubble', 'x'))
e = es[0]
G.equipped_weapon = 'shortbow'
G.update_derived_stats()
roll = 10
e.update(dist='far', in_cover=True, ranged=True,
         ac=roll + G.player_attack_bonus + 2)      # quick attack: +2 to hit
hp_before = e['hp']
random.randint = lambda a, b: roll
G.do_quick_attack()
random.randint = _orig_randint
check("enemy cover raises its effective AC against your shots", e['hp'] == hp_before)
check("...and the log blames the obstacle", any('smacks into' in m for m in logs[-4:]))
G.equipped_weapon = 'longsword'
G.update_derived_stats()

# =================== 6. Enemy AI: kiting, rushing, pack tactics ============
es = fresh_fight(G.make_enemy_pack(1, count=2))
e0 = es[0]
e0.update(ranged=True, dist='near', retreats_left=1, atk=30, fearless=False)
e0['hp'] = int(e0['max_hp'] * 0.4)                 # hurt: wants to kite
hp_before = G.health
ok = G.enemy_take_turn(e0)
check("hurt skirmisher falls back instead of attacking",
      ok and e0['dist'] == 'far' and e0['retreats_left'] == 0 and G.health == hp_before)

e1 = es[1]
e1.update(ranged=False, dist='far', atk=-30)
G.enemy_take_turn(e1)
check("melee straggler rushes in (and still swings)", e1['dist'] == 'near')

es = fresh_fight(G.make_enemy_pack(1, count=3))
for e in es:
    e.update(ranged=False, dist='near', atk=-30, fearless=True)
G._pack_tactics_on = False
G.enemy_take_turn(es[0])
check("pack tactics announced when melee gang up", G._pack_tactics_on)

# =================== 7. Morale: a broken pack's survivor bolts =============
es = fresh_fight(G.make_enemy_pack(1, count=2))
es[1]['hp'] = 0                                    # pack broken
e0 = es[0]
e0.update(fearless=False)
e0['hp'] = max(1, int(e0['max_hp'] * 0.2))         # badly hurt
xp_before = G.xp + 0
_orig_random = random.random
random.random = lambda: 0.0                        # force the morale roll
G.enemy_take_turn(e0)
random.random = _orig_random
check("broken morale: the survivor flees", e0['hp'] == 0 and e0.get('fled'))
check("fleeing ends the fight when it was the last one", not G.in_combat)
check("you get a little XP for breaking them", any('bolts into the dark' in m for m in logs))

# =================== 8. Boss telegraphs =====================================
boss_pack = G.make_boss(4)
boss = boss_pack[0]
boss['atk'] = -30
for m in boss_pack[1:]:
    m['atk'] = -30
fresh_fight(boss_pack)
expected = game.TELEGRAPHS[boss['special']].format(name=boss['name'])
logs.clear()
G.end_turn()
pump_enemies()
check("boss telegraphs its special one round early", any(expected in m for m in logs),
      boss['special'])

# =================== 9. Cover halves a boss's breath ========================
wyrm = None
for _ in range(40):
    cand = G.make_boss(13)[0]
    if cand['special'] == 'breath':
        wyrm = cand
        break
fresh_fight([wyrm], obstacle=('an old barricade', 'x'))
G.player_in_cover = True
G.temp_hp = 0
hp_before = G.health
random.randint = lambda a, b: 4                    # 6d6 of 4s = 24 -> halved 12
_r = random.random
random.random = lambda: 0.9                        # the barricade survives
G.boss_special(wyrm)
random.randint = _orig_randint
random.random = _r
check("bracing behind cover halves the breath", hp_before - G.health == 12,
      f"lost {hp_before - G.health}")

# =================== 10. Companions =========================================
G.escape_combat()
G.companion = None
gold_before = G.gold
check("hiring works (free rescue path)", G.hire_companion('field medic', free=True))
check("free hires cost nothing", G.gold == gold_before)
check("only one companion at a time", not G.hire_companion('archer', free=True))

es = fresh_fight(G.make_enemy_pack(1, count=1))
es[0]['atk'] = -30
G.health = int(G.max_health * 0.4)
hp_before = G.health
G.end_turn()
check("the medic patches you up before the enemies move", G.health > hp_before)
pump_enemies()

# an archer thins the pack on its own
G.companion = None
G.hire_companion('archer', free=True)
es = fresh_fight(G.make_enemy_pack(1, count=1))
es[0].update(atk=-30, ac=0)
es[0]['hp'] = es[0]['max_hp'] = 200                # big enough to survive the shot
hp_before = es[0]['hp']
G.end_turn()
check("the archer takes its shot after you end your turn", es[0]['hp'] < hp_before)
pump_enemies()

# interception: the ally takes a hit meant for you
es = fresh_fight(G.make_enemy_pack(1, count=1))
e = es[0]
e.update(atk=30, ranged=False, dist='near')
comp_hp = G.companion['hp']
hp_before = G.health
random.random = lambda: 0.0                        # force the intercept
G.enemy_single_attack(e)
random.random = _orig_random
took_it = (G.companion is None) or (G.companion['hp'] < comp_hp)
check("the companion steps in front of an attack", took_it and G.health == hp_before)

# saves carry the companion and the adaptive dial
G.escape_combat()
G.companion = None
G.hire_companion('sellsword', free=True)
G.adaptive_mult = 0.91
import json
st = json.loads(json.dumps(G.game_state_dict()))
name_saved = G.companion['name']
G.companion = None
G.adaptive_mult = 1.0
G.apply_game_state(st)
check("save/load keeps the companion", G.companion and G.companion['name'] == name_saved)
check("save/load keeps the adaptive dial", abs(G.adaptive_mult - 0.91) < 1e-9)

# =================== 11. Adaptive difficulty ================================
G.adaptive_enabled = True
G.recent_fights = []
G.adaptive_mult = 1.0
G.max_health = 30
for _ in range(4):                                  # four brutal fights
    G._fight_hp_start = 30
    G.health = 2
    G._fight_round_count = 5
    G.record_fight_result(died=False)
check("struggling eases the dial down", G.adaptive_mult < 1.0, G.adaptive_mult)
low = G.adaptive_mult
for _ in range(12):                                 # then a long cruise
    G._fight_hp_start = 30
    G.health = 30
    G._fight_round_count = 3
    G.record_fight_result(died=False)
check("cruising firms the dial back up", G.adaptive_mult > low, G.adaptive_mult)
check("the dial respects its bounds",
      game.ADAPTIVE_MIN <= G.adaptive_mult <= game.ADAPTIVE_MAX)
check("the window forgets old fights", len(G.recent_fights) == game.ADAPTIVE_WINDOW)

# =================== 12. Narrator hooks =====================================
# Spy on narrate() to prove the game speaks the right things at the right
# moments - without ever spawning a real voice in a headless run.
G.quick_start_class('Fighter', level=3)
G.companion = None
spoken = []
G.narrate = lambda text: spoken.append(str(text))

# one damage summary per round, spoken at the top of your next turn
es = fresh_fight(G.make_enemy_pack(1, count=1))
es[0].update(atk=30, dist='near', ranged=False, attacks=1, dmg=4)
spoken.clear()
G.end_turn()
pump_enemies()
check("narrator sums the round's damage into one line",
      any('You took' in s and 'health left' in s for s in spoken), spoken)

# kills speak, and the last one becomes Victory
es = fresh_fight(G.make_enemy_pack(1, count=2))
for e in es:
    e['atk'] = -30
spoken.clear()
G.hit_enemy(es[0], 999)
check("a kill gets a short callout", any('down.' in s for s in spoken), spoken)
G.hit_enemy(es[1], 999)
check("clearing the room says Victory", any('Victory' in s for s in spoken), spoken)

# the boss telegraph gets a spoken warning
boss_pack = G.make_boss(4)
for b in boss_pack:
    b['atk'] = -30
fresh_fight(boss_pack)
spoken.clear()
G.end_turn()
pump_enemies()
check("boss wind-up is spoken as a warning",
      any('Big attack coming' in s for s in spoken), spoken)
G.escape_combat()

# level ups speak
spoken.clear()
G.add_xp(G.xp_to_next)
check("level ups are announced", any(s.startswith('Level ') for s in spoken), spoken)

# out-of-combat damage (traps, poison) speaks immediately
spoken.clear()
G.in_combat = False
G.damage_player(3, "A dart snaps out of the wall.")
check("out-of-combat damage speaks right away",
      any('You take 3 damage' in s for s in spoken), spoken)

# gating: the REAL narrate never starts a voice while sound is off (all
# harnesses set sound_enabled False, so headless runs stay silent)
del G.narrate                       # un-shadow the real method
G.sound_enabled = False
G.narrator_enabled = True
G._narr_queue = None
G._narr_thread = None
G.narrate("this must go nowhere")
check("narrator obeys the master sound switch (no worker spawned)",
      G._narr_queue is None and G._narr_thread is None)
G.narrator_enabled = False
G.sound_enabled = True
G._narr_backend = 'espeak'          # pretend a voice exists
G.narrate("still nowhere")
check("narrator toggle alone also silences it",
      G._narr_queue is None and G._narr_thread is None)
G.narrator_enabled = True
G.sound_enabled = False
G._narr_backend = '?'

print()
if fails:
    print(f"{len(fails)} FAILURES:")
    for f in fails:
        print("  ", f)
    sys.exit(1)
print("ALL TACTICS CHECKS PASSED")
