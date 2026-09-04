"""Headless checks for subclasses.

Data sanity, the effects actually reaching AC / crits / max HP through
gear_effects, random assignment, save/load, and the Path pickers in the
creator and the main menu.

Run:  xvfb-run -a python3 test_subclasses.py
"""
import importlib.util
import json
import random
import tkinter as tk
from tkinter import ttk

spec = importlib.util.spec_from_file_location("game", "mane_game.py")
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)

game.TinyAdventureGUI.init_sounds = lambda self: None
game.TinyAdventureGUI.play_sound = lambda self, *a, **k: None
game.TinyAdventureGUI.show_dice_roll = lambda self, *a, **k: None

failures = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


root = tk.Tk()
G = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI)
G.__init__(root)
G.sound_enabled = False
G.music_enabled = False
root.update()
for w in list(root.winfo_children()):
    if isinstance(w, tk.Toplevel):
        w.destroy()
root.update()

# ------------------------------------------------------------- data sanity
ALLOWED = {'desc', 'ac', 'atk', 'dmg', 'spell_atk', 'max_hp', 'max_hp_per_level',
           'dr', 'regen', 'check_bonus', 'flee_bonus', 'crit_range', 'stat',
           'slot_bonus', 'bonus_damage', 'damage_type', 'light'}
ok_classes = all(len(game.SUBCLASSES.get(cls, {})) >= 2 for cls in game.CLASSES)
check("every class has at least two subclasses", ok_classes,
      {cls: len(game.SUBCLASSES.get(cls, {})) for cls in game.CLASSES})
bad_keys = [(cls, sub, k) for cls, subs in game.SUBCLASSES.items()
            for sub, info in subs.items() for k in info if k not in ALLOWED]
check("every subclass uses only understood effect keys", not bad_keys, bad_keys)
no_desc = [(cls, sub) for cls, subs in game.SUBCLASSES.items()
           for sub, info in subs.items() if not info.get('desc')]
check("every subclass has a description", not no_desc, no_desc)

# --------------------------------------------- effects reach derived stats
random.seed(7)
G.quick_start_class('Fighter', level=3, subclass='Champion')
check("explicit subclass is applied", G.subclass == 'Champion', G.subclass)
check("Champion crits on 19 via gear_effects",
      G.gear_effects().get('crit_range') == 19)

# same seed, both wizard schools: Abjuration is exactly +1 AC over Evocation
random.seed(11)
G.quick_start_class('Wizard', level=3, subclass='School of Evocation')
ac_evo = G.player_ac
random.seed(11)
G.quick_start_class('Wizard', level=3, subclass='School of Abjuration')
ac_abj = G.player_ac
check("Abjuration grants exactly +1 AC over Evocation (same rolls)",
      ac_abj == ac_evo + 1, f"{ac_evo} vs {ac_abj}")
check("Abjuration's damage reduction reaches the derived stat",
      G.damage_reduction >= 1, G.damage_reduction)

# max_hp_per_level scales: Draconic vs Wild Magic at level 5 differ by 5 HP
random.seed(13)
G.quick_start_class('Sorcerer', level=5, subclass='Wild Magic')
hp_wild = G.max_health
random.seed(13)
G.quick_start_class('Sorcerer', level=5, subclass='Draconic Bloodline')
hp_drac = G.max_health
check("Draconic Bloodline adds +1 max HP per level (5 at level 5)",
      hp_drac == hp_wild + 5, f"{hp_wild} vs {hp_drac}")

# ------------------------------------------------------ defaults + safety
random.seed(17)
G.quick_start_class('Rogue', level=2)
check("no choice still lands a valid path of the right class",
      G.subclass in game.SUBCLASSES['Rogue'], G.subclass)
G.subclass = None
G.update_derived_stats()
check("no subclass at all is safe (old saves)", G.subclass_effects() == {})

# ---------------------------------------------------------- persistence
random.seed(19)
G.quick_start_class('Cleric', level=4, subclass='Life Domain')
hp_before, regen = G.max_health, G.gear_effects().get('regen', 0)
check("Life Domain regeneration flows through", regen >= 1, regen)
state = json.loads(json.dumps(G.game_state_dict()))
check("subclass is in the save", state.get('subclass') == 'Life Domain',
      state.get('subclass'))
G.subclass = None
G.apply_game_state(state)
check("subclass survives a save/load round trip", G.subclass == 'Life Domain',
      G.subclass)
G.update_derived_stats()
check("effects intact after loading", G.max_health == hp_before,
      f"{hp_before} vs {G.max_health}")
old_state = {k: v for k, v in state.items() if k != 'subclass'}
G.apply_game_state(json.loads(json.dumps(old_state)))
check("a pre-subclass save loads as no path", G.subclass is None, G.subclass)

# ------------------------------------------------- the creator's Path row
G.open_character_creator()
root.update()
creator = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
combos = [w for w in walk(creator) if isinstance(w, ttk.Combobox)]
path_combo = [c for c in combos if 'Path of the Berserker'
              in c.cget('values') or 'Champion' in c.cget('values')]
check("creator has a Path picker", len(path_combo) == 1, len(path_combo))
if path_combo:
    pc = path_combo[0]
    check("Fighter paths offered by default",
          tuple(pc.cget('values')) == tuple(game.SUBCLASSES['Fighter'])
          and pc.get() == 'Champion', pc.cget('values'))
    class_combo = [c for c in combos if 'Wizard' in c.cget('values')][0]
    class_combo.set('Wizard')
    class_combo.event_generate('<<ComboboxSelected>>')
    root.update()
    check("switching class swaps the offered paths",
          tuple(pc.cget('values')) == tuple(game.SUBCLASSES['Wizard']), pc.cget('values'))
    descs = [w for w in walk(creator) if isinstance(w, ttk.Label)
             and 'arcane' in str(w.cget('text')).lower()
             or isinstance(w, ttk.Label) and 'destruction' in str(w.cget('text')).lower()]
    check("the picked path shows its description", len(descs) >= 1)
creator.destroy()
root.update()

# ------------------------------------------------ the menu's Path dropdown
G.open_main_menu()
root.update()
menu = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
qs_combos = [w for w in walk(menu) if isinstance(w, ttk.Combobox)]
qs_path = [c for c in qs_combos if '(random)' in c.cget('values')]
check("menu Quick Start offers a Path dropdown", len(qs_path) == 1, len(qs_path))
if qs_path:
    qp = qs_path[0]
    check("it defaults to (random)", qp.get() == '(random)')
    qs_class = [c for c in qs_combos if 'Barbarian' in c.cget('values')][0]
    qs_class.set('Barbarian')
    qs_class.event_generate('<<ComboboxSelected>>')
    root.update()
    check("class change repopulates the paths",
          'Path of the Berserker' in qp.cget('values'), qp.cget('values'))
menu.destroy()
root.update()

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    raise SystemExit(1)
print("ALL SUBCLASS CHECKS PASSED")
