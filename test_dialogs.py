"""Open every dialog that changed, to catch runtime errors in the UI paths."""
import tkinter as tk, importlib.util, random, sys
spec = importlib.util.spec_from_file_location("game", "mane_game.py")
game = importlib.util.module_from_spec(spec); spec.loader.exec_module(game)
game.TinyAdventureGUI.init_sounds = lambda self: None

root = tk.Tk()
G = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI)
G.__init__(root)
G.sound_enabled = False; G.music_enabled = False
errors = []

def try_open(label, fn, closer=None):
    before = set(root.winfo_children())
    try:
        fn()
        root.update()
        new = [w for w in root.winfo_children() if w not in before and isinstance(w, tk.Toplevel)]
        # walk every widget so geometry/text errors surface
        for w in new:
            for child in w.winfo_children():
                child.winfo_children()
        print(f"PASS  {label}  ({len(new)} window(s))")
        for w in new:
            w.grab_release(); w.destroy()
        root.update()
    except Exception as e:
        import traceback; traceback.print_exc()
        errors.append(f"{label}: {e}")
        print(f"FAIL  {label}: {e}")

random.seed(42)
try_open("main menu", G.open_main_menu)
try_open("character creator", G.open_character_creator)
try_open("settings (volume sliders)", G.open_settings)

G.quick_start_class('Wizard', level=5)
try_open("spellbook out of combat", G.open_spellbook)
try_open("stats", G.show_stats)
try_open("help", G.show_help)
try_open("rest", G.do_rest)

G.pending_enemies = G.make_enemy_pack(1, count=2)
G.current_event = 'enemy'
G.do_attack()
try_open("spellbook in combat", G.open_spellbook)
try_open("bonus action menu", G.open_bonus_menu)
try_open("class ability (wizard)", G.use_class_ability)
try_open("level-up spell learning", lambda: G.open_spell_learning(1, 2, 3))

for cls in game.CLASSES:
    random.seed(1)
    G.quick_start_class(cls, level=3)
    try:
        G.refresh_stats(); G.refresh_inventory(); G.refresh_buttons(); root.update()
    except Exception as e:
        errors.append(f"{cls} refresh: {e}"); print(f"FAIL  {cls} refresh: {e}")
print("PASS  all 12 classes build and render")

# generic class menus
for cls in ('Barbarian','Bard','Cleric','Druid','Monk','Paladin','Ranger','Rogue','Fighter','Sorcerer','Warlock'):
    random.seed(2)
    G.quick_start_class(cls, level=3)
    G.pending_enemies = G.make_enemy_pack(1, count=1); G.current_event='enemy'; G.do_attack()
    try_open(f"class ability menu: {cls}", G.use_class_ability)

print()
if errors:
    print(f"{len(errors)} FAILURES"); sys.exit(1)
print("ALL DIALOGS OK")
