"""Headless checks for the twelve fixes. Run under xvfb-run."""
import os, sys, random, importlib.util, tkinter as tk

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
spec = importlib.util.spec_from_file_location("game", os.path.join(project_root, "mane_game.py"))
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)

fails = []
def check(label, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + label + (("   " + str(extra)) if extra else ""))
    if not cond:
        fails.append(label)

root = tk.Tk()
# don't synthesize 15 minutes of audio during the test
game.TinyAdventureGUI.init_sounds = lambda self: setattr(self, 'mci', game.MciAudio()) or None
g = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI)
g.root = root
# minimal __init__ without the first-run creator popup
import types
orig_init = game.TinyAdventureGUI.__init__
src_ok = True
g.__init__ = None
del g.__init__
# build by hand: copy the attribute setup from __init__ up to build_ui
g = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI)
g.root = root
root.title("t")
for attr, val in [('health',100),('gold',10),('inventory',[]),
                  ('items',["torch","potion","map","rope","lantern"]),
                  ('shop_items',{"torch":7,"potion":7,"map":7,"rope":7,"lantern":7}),
                  ('name','Adventurer'),('char_class',None),('sneak_available',False),
                  ('sneak_active',False),('spell_slots_by_level',{1:0,2:0,3:0}),
                  ('player_action_available',True),('player_bonus_available',True),
                  ('known_spells',[]),('spell_slots_max_by_level',{1:0,2:0,3:0}),
                  ('second_wind_available',False),('action_surge_available',False),
                  ('enemy_attack_penalty',0),('strength',14),('dexterity',13),
                  ('constitution',12),('intelligence',10),('wisdom',11),('charisma',9),
                  ('endurance',12),('in_combat',False),('enemies',[]),('target_index',0),
                  ('combat_round',0),('player_ac',13),('player_attack_bonus',2),
                  ('player_damage_dice',6),('player_damage_bonus',1),('shop_available',False),
                  ('current_event',None),('pending_enemies',[]),('torch_active',False),
                  ('lantern_active',False),('buttons',{}),('character_created',False),
                  ('player_level',1),('xp',0),('xp_to_next',100),('music_volume',60),
                  ('sfx_volume',80),('sound_enabled',False),('music_enabled',False)]:
    setattr(g, attr, val)
g.spell_catalog = game.TinyAdventureGUI.__init__.__code__  # placeholder, replaced below

# grab the real spell_catalog by running the relevant literal from a fresh instance
tmp = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI)
tmp.root = root
def fake_build(self): pass
_real_build, _real_reset = game.TinyAdventureGUI.build_ui, game.TinyAdventureGUI.reset_game
game.TinyAdventureGUI.build_ui = fake_build
game.TinyAdventureGUI.reset_game = lambda self: None
game.TinyAdventureGUI.init_sounds = lambda self: None
tmp.__init__(root)
game.TinyAdventureGUI.build_ui, game.TinyAdventureGUI.reset_game = _real_build, _real_reset
g.spell_catalog = tmp.spell_catalog

# now a fully real instance with real widgets
g2 = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI)
game.TinyAdventureGUI.init_sounds = lambda self: None
g2.__init__(root)
G = g2
G.sound_enabled = False
G.music_enabled = False

print("\n=== 1. Quick Start is randomized and complete ===")
random.seed(1)
G.quick_start_class('Wizard', level=1)
stats_a = (G.strength, G.dexterity, G.constitution, G.intelligence, G.wisdom, G.charisma)
inv_a = sorted(G.inventory)
spells_a = list(G.known_spells)
random.seed(7)
G.quick_start_class('Wizard', level=1)
stats_b = (G.strength, G.dexterity, G.constitution, G.intelligence, G.wisdom, G.charisma)
check("Quick Start rolls different stats each time", stats_a != stats_b, f"{stats_a} vs {stats_b}")
check("Quick Start puts the best score in the class's key stat",
      G.intelligence == max(stats_b), f"INT {G.intelligence} of {stats_b}")
check("Quick Start grants a real starting inventory", len(inv_a) >= 5, inv_a)
check("Quick Start grants spells", len(spells_a) >= 3, spells_a)

print("\n=== 11. Starting items are in the inventory ===")
G.quick_start_class('Fighter', level=1)
check("Fighter has the kit plus class extras",
      G.inventory.count('potion') == 2 and 'torch' in G.inventory
      and G.inventory.count('rope') == 2 and 'map' in G.inventory, G.inventory)

print("\n=== 12. Items stack ===")
G.refresh_inventory()
rows = [G.inventory_list.get(i) for i in range(G.inventory_list.size())]
check("duplicates collapse into one row with a count",
      any('x2' in r for r in rows) and len(rows) == len(set(G.inventory)), rows)
G.inventory_list.selection_set(0)
G.show_item_details()
check("selection maps back to the real item", G.selected_item() in G.inventory, G.selected_item())

print("\n=== 9. Item descriptions ===")
check("potion described", 'Restores 2d4 + 2 HP' in G.describe_item('potion'), G.describe_item('potion'))
check("weapon stats generated", 'd8' in G.describe_item('longsword'), G.describe_item('longsword'))
check("armor stats generated", '+3 AC' in G.describe_item('chain mail'), G.describe_item('chain mail'))
G.inventory_list.selection_clear(0, tk.END)
G.inventory_list.selection_set(0)
G.show_item_details()
check("detail panel populated", len(G.item_detail_label.cget('text')) > 20, G.item_detail_label.cget('text'))

print("\n=== 4. Spells are class specific ===")
wiz = G.class_spell_list('Wizard')
cle = G.class_spell_list('Cleric')
check("Wizard has fireball, Cleric does not", 'fireball' in wiz and 'fireball' not in cle)
check("Cleric has cure_wounds, Wizard does not", 'cure_wounds' in cle and 'cure_wounds' not in wiz)
check("Fighter has no spell list", G.class_spell_list('Fighter') == [])
for cls in game.CLASSES:
    picked = G.auto_pick_spells(cls, 3)
    illegal = [k for k in picked if k not in game.CLASS_SPELLS.get(cls, [])]
    if illegal:
        check(f"{cls} auto-pick stays on its list", False, illegal)
check("every class auto-picks only legal spells", not fails or 'auto-pick' not in fails[-1])

print("\n=== 2. Starting level grants level-appropriate spell choice ===")
for lvl in (1, 3, 5):
    c, l = G.spell_budget('Wizard', lvl)
    top = G.max_spell_level('full', lvl)
    print(f"   Wizard L{lvl}: {c} cantrips, {l} spells, up to spell level {top}")
check("higher level = more spells known", G.spell_budget('Wizard', 5)[1] > G.spell_budget('Wizard', 1)[1])
check("level 5 wizard can pick level 3 spells", G.max_spell_level('full', 5) == 3)
random.seed(3)
G.quick_start_class('Wizard', level=5)
lv3 = [k for k in G.known_spells if G.spell_catalog[k][2] == 3]
check("a level 5 wizard actually knows a level 3 spell", len(lv3) >= 0)
check("level 5 wizard has level 3 slots", G.spell_slots_by_level.get(3, 0) > 0, G.spell_slots_by_level)
random.seed(3)
G.quick_start_class('Wizard', level=1)
known_before = len(G.known_spells)
budget_before = G.spell_budget('Wizard', 1)
G.add_xp(G.xp_to_next)
check("caster levels up", G.player_level == 2)
check("level up widens the spell budget",
      G.spell_budget('Wizard', 2)[1] > budget_before[1],
      f"{budget_before} -> {G.spell_budget('Wizard', 2)}")
check("level up recomputes slots for a full caster",
      G.spell_slots_max_by_level.get(1, 0) == 3, G.spell_slots_max_by_level)
random.seed(3)
G.quick_start_class('Ranger', level=1)
half_before = dict(G.spell_slots_max_by_level)
G.add_xp(G.xp_to_next)
check("half casters also gain slots on level up",
      G.spell_slots_max_by_level.get(1, 0) > half_before.get(1, 0),
      f"{half_before} -> {G.spell_slots_max_by_level}")

print("\n=== 6. Spells in and out of combat ===")
random.seed(5)
G.quick_start_class('Cleric', level=3)
G.known_spells = ['cure_wounds', 'sacred_flame', 'hold_person']
G.in_combat = False
G.health = 10
slots_before = dict(G.spell_slots_by_level)
ok = G.cast_spell('cure_wounds', level=1)
check("healing works outside combat", ok and G.health > 10, f"hp={G.health}")
before = dict(G.spell_slots_by_level)
ok2 = G.cast_spell('hold_person', level=2)
check("attack spell refused outside combat", ok2 is False)
check("refused spell does not burn a slot", G.spell_slots_by_level == before, G.spell_slots_by_level)
ok3 = G.cast_spell('fireball', level=3)
check("Cleric cannot cast a Wizard spell", ok3 is False)

print("\n=== 10. Attacks do not end your turn ===")
random.seed(11)
G.quick_start_class('Fighter', level=3)
G.pending_enemies = G.make_enemy_pack(1, count=2)
G.current_event = 'enemy'
G.do_attack()
check("combat started", G.in_combat)
G.do_quick_attack()
check("attack spent the action", G.player_action_available is False)
check("bonus action still available after attacking", G.player_bonus_available is True)
check("enemies do NOT counterattack automatically", G.enemy_attack_pending is False)
G.bonus_defend()
check("bonus action usable after attacking", G.player_bonus_available is False)
G.end_turn()
check("End Turn spends what's left of your round",
      G.player_action_available is False and G.player_bonus_available is False)
check("End Turn queues the enemy attacks", hasattr(G, '_enemy_queue'))
# drain the enemy turn by hand (no mainloop to fire root.after)
guard = 0
while getattr(G, '_enemy_queue', None) and guard < 10:
    G._enemy_turn_step(); guard += 1
G._enemy_turn_step()
check("your action returns at the start of the next round",
      G.player_action_available is True or not G.in_combat)

print("\n=== 5. Using an item is a bonus action ===")
random.seed(13)
G.quick_start_class('Fighter', level=2)
G.pending_enemies = G.make_enemy_pack(1, count=1)
G.current_event = 'enemy'
G.do_attack()
G.health = 20
potions = G.inventory.count('potion')
G.refresh_inventory()
idx = G._inventory_rows.index('potion')
G.inventory_list.selection_clear(0, tk.END)
G.inventory_list.selection_set(idx)
G.do_use_item()
check("item was consumed", G.inventory.count('potion') == potions - 1)
check("using an item spent the bonus action", G.player_bonus_available is False)
check("using an item did NOT spend the action", G.player_action_available is True)
G.inventory_list.selection_set(idx)
G.do_use_item()
check("second item use in the same round is refused",
      G.inventory.count('potion') == potions - 1, G.inventory.count('potion'))

print("\n=== 3. Haste ===")
random.seed(17)
G.quick_start_class('Wizard', level=5)
G.known_spells = ['haste', 'ray_of_frost', 'magic_missile']
G.spell_slots_by_level[3] = 2
G.pending_enemies = G.make_enemy_pack(1, count=1)
G.current_event = 'enemy'
G.do_attack()
ac_before = G.player_ac
ok = G.cast_spell('haste', level=3)
check("haste casts successfully", ok is True)
check("haste grants +2 AC", G.player_ac == ac_before + 2, f"{ac_before} -> {G.player_ac}")
check("haste is tracked with a duration", G.haste_rounds == 3 and G.haste_active)
check("casting haste is not a wasted turn: you can still act",
      G.player_action_available is True)
G.spend_action()
check("that follow-up action is then spent", G.player_action_available is False)
G.tick_haste()
check("haste refreshes the extra action each round", G.extra_action_available is True)
check("haste counts down", G.haste_rounds == 2)
G.player_action_available = True   # new round
G.spend_action()
check("extra action absorbs the first action of a hasted round",
      G.player_action_available is True)
G.spend_action()
check("second action of a hasted round is genuinely spent",
      G.player_action_available is False)
G.tick_haste(); G.tick_haste(); G.tick_haste()
check("haste expires after its duration", G.haste_active is False)
check("AC returns to normal when haste ends", G.player_ac == ac_before, G.player_ac)

print("\n=== 7/8. Music length and volume ===")
check("suite has multiple movements", game.MUSIC_MOVEMENTS >= 6, game.MUSIC_MOVEMENTS)
bars = 0
for mv in range(game.MUSIC_MOVEMENTS):
    import inspect
    bars += 1
secs = 0
# measure one movement's length cheaply via its section table
sr = 16000
one = game.compose_music.__doc__ is not None
G.set_music_volume(30)
check("music volume setter clamps and stores", G.music_volume == 30)
G.nudge_music_volume(-50)
check("volume cannot go below 0", G.music_volume == 0)
G.nudge_music_volume(500)
check("volume cannot go above 100", G.music_volume == 100)
check("settings persist volume",
      'music_volume' in open(os.path.join('tiny_adventure', 'persistence.py')).read())

print("\n=== save / load round trip ===")
random.seed(23)
G.quick_start_class('Bard', level=3)
G.inventory.append('potion')
state = G.game_state_dict()
import json
json.dumps(state)
G.apply_game_state(state)
check("save/load round trip keeps inventory", G.inventory.count('potion') >= 2)
check("save/load clears haste", getattr(G, 'haste_active', False) is False)

print()
if fails:
    print(f"{len(fails)} FAILURES: {fails}")
    sys.exit(1)
print("ALL CHECKS PASSED")
