"""Headless checks for the UI overhaul.

Covers the four reported problems:
 1. white-on-white fields (spinboxes / comboboxes were unreadable)
 2. dialogs opening at the wrong size / off the screen (the creator especially)
 3. the character creator's stat pool losing rolls on a misclick
 4. too many separate windows (sheet / spellbook / gear are one tabbed window)

Run with a small screen so the clamping is actually exercised:
      xvfb-run -a -s "-screen 0 1366x768x24" python3 tests/test_ui_fixes.py
"""
import importlib.util
import os
import tkinter as tk
from tkinter import ttk

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("game", os.path.join(project_root, "mane_game.py"))
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)

# silence audio just like the other harnesses
game.TinyAdventureGUI.init_sounds = lambda self: None
game.TinyAdventureGUI.play_sound = lambda self, *a, **k: None
game.TinyAdventureGUI.start_music = lambda self, *a, **k: None
game.TinyAdventureGUI.stop_music = lambda self, *a, **k: None
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


def buttons_by_text(top, text):
    return [w for w in walk(top) if isinstance(w, ttk.Button)
            and w.cget('text') == text]


def pool_buttons(creator):
    return [b for b, _v in creator.roll_buttons]


def stat_row_widgets(creator, stat):
    """(value button, assign button) for one ability row, found via its label."""
    for w in walk(creator):
        if isinstance(w, ttk.Label) and w.cget('text') == f"{stat}:":
            row = w.master
            btns = [c for c in row.winfo_children() if isinstance(c, ttk.Button)]
            value_btn = [b for b in btns if b.cget('text') != 'Assign'][0]
            assign_btn = [b for b in btns if b.cget('text') == 'Assign'][0]
            return value_btn, assign_btn
    raise AssertionError(f"no row for {stat}")


root = tk.Tk()
G = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI)
G.__init__(root)
G.sound_enabled = False
G.music_enabled = False
G.root.update()
# the app opens its own main menu at startup; clear the stage first
for w in list(G.root.winfo_children()):
    if isinstance(w, tk.Toplevel):
        w.destroy()
G.root.update()
sw, sh = G.root.winfo_screenwidth(), G.root.winfo_screenheight()
print(f"screen: {sw}x{sh}")

# ------------------------------------------------- 1. readable field styling
style = ttk.Style(G.root)
p = G.PAL
check("TSpinbox field is dark (was unstyled white)",
      style.lookup('TSpinbox', 'fieldbackground') == p['field'],
      style.lookup('TSpinbox', 'fieldbackground'))
check("TSpinbox text is parchment",
      style.lookup('TSpinbox', 'foreground') == p['text'])
check("TCombobox readonly field stays dark",
      style.lookup('TCombobox', 'fieldbackground', ['readonly']) == p['field'])
check("TEntry field is dark", style.lookup('TEntry', 'fieldbackground') == p['field'])
_probe = tk.Entry(G.root)
check("plain tk.Entry fallback readable (dark field, parchment text)",
      _probe.cget('background') == p['field'] and _probe.cget('foreground') == p['text'],
      f"{_probe.cget('background')}/{_probe.cget('foreground')}")
_probe.destroy()
_probe = tk.Listbox(G.root)
check("plain tk.Listbox fallback readable",
      _probe.cget('background') == p['field'] and _probe.cget('foreground') == p['text'])
_probe.destroy()

# ------------------------------------- 2 + 3. the creator: fits, and forgives


def creator_window():
    tops = [w for w in G.root.winfo_children() if isinstance(w, tk.Toplevel)]
    return tops[-1]


def fits(win, label):
    win.update_idletasks()
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    check(label, x >= 0 and y >= 0 and x + w <= sw and y + h <= sh,
          f"{w}x{h}+{x}+{y} on {sw}x{sh}")


G.open_character_creator()
G.root.update()
creator = creator_window()
fits(creator, "creator opens fully on a 1366x768 screen")

# switch to a caster at level 5: the spell list must appear inline, no 2nd window
combo = [w for w in walk(creator) if isinstance(w, ttk.Combobox)][0]
combo.set('Wizard')
combo.event_generate('<<ComboboxSelected>>')
G.root.update()
spin = [w for w in walk(creator) if isinstance(w, ttk.Spinbox)][0]
spin.set(5)
spin.event_generate('<KeyRelease>')
G.root.update()

tops = [w for w in G.root.winfo_children() if isinstance(w, tk.Toplevel)]
check("choosing spells opens NO second window", len(tops) == 1, f"{len(tops)} windows")
spell_boxes = [w for w in walk(creator) if isinstance(w, ttk.Checkbutton)]
check("spell checkboxes are inline in the creator", len(spell_boxes) > 5,
      f"{len(spell_boxes)} boxes")
fits(creator, "creator still fits with the Wizard L5 spell list showing")

# --- the stat pool: misclicks must not eat rolls ---
pools = pool_buttons(creator)
check("pool auto-rolled six values on open", len(pools) == 6, f"{len(pools)}")
before_vals = sorted(b.cget('text') for b in pools)

v_str, a_str = stat_row_widgets(creator, 'STR')
v_dex, a_dex = stat_row_widgets(creator, 'DEX')

pools[0].invoke()
a_str.invoke()
G.root.update()
check("assigning a roll fills the ability", v_str.cget('text') == pools[0].cget('text'))
check("assigned roll leaves the pool", pools[0].instate(['disabled']))

# the old bug: re-assigning STR orphaned the first roll forever
pools[1].invoke()
a_str.invoke()
G.root.update()
check("re-assigning frees the old roll back to the pool (the reported bug)",
      not pools[0].instate(['disabled']))
check("ability shows the new roll", v_str.cget('text') == pools[1].cget('text'))

# clicking a placed number takes it back and picks it up again
v_str.invoke()
G.root.update()
check("clicking a placed number un-assigns it", v_str.cget('text') == '-')
check("that roll returns to the pool", not pools[1].instate(['disabled']))
check("and is picked up, ready to re-point",
      creator.selected_roll is not None and creator.selected_roll[0] is pools[1])
a_dex.invoke()
G.root.update()
check("re-pointing the taken-back number works",
      v_dex.cget('text') == pools[1].cget('text'))

# Clear Assignments must keep the same six rolls (it used to re-roll them)
buttons_by_text(creator, "Clear Assignments")[0].invoke()
G.root.update()
after_vals = sorted(b.cget('text') for b in pool_buttons(creator))
check("Clear Assignments keeps the same six rolls", after_vals == before_vals,
      f"{before_vals} -> {after_vals}")
check("all abilities cleared",
      all(stat_row_widgets(creator, s)[0].cget('text') == '-'
          for s in ("STR", "DEX", "CON", "INT", "WIS", "CHA")))
enabled = [b for b in pool_buttons(creator) if not b.instate(['disabled'])]
check("every roll usable again after Clear", len(enabled) == 6, f"{len(enabled)}")

creator.destroy()
G.root.update()

# ------------------------------------------ 4. one tabbed character window
G.quick_start_class('Wizard', level=5)
G.root.update()

G.show_stats()
G.root.update()
sheet1 = G._sheet_win
check("Stats opens the character window", sheet1.winfo_exists())
fits(sheet1, "character window fits the screen")

G.open_spellbook()
G.root.update()
tops = [w for w in G.root.winfo_children() if isinstance(w, tk.Toplevel)]
check("Spellbook reuses the same window (no stacking)",
      G._sheet_win is sheet1 and len(tops) == 1, f"{len(tops)} windows")
check("...switched to the Spellbook tab",
      G._sheet_nb.index(G._sheet_nb.select()) == 1)

G.open_equipment_window()
G.root.update()
check("Gear switches the same window to its tab",
      G._sheet_win is sheet1 and G._sheet_nb.index(G._sheet_nb.select()) == 2)

sheet1.destroy()
G.root.update()
G.open_spellbook()
G.root.update()
check("window recreates cleanly after being closed",
      G._sheet_win.winfo_exists() and G._sheet_win is not sheet1
      and G._sheet_nb.index(G._sheet_nb.select()) == 1)
G._sheet_win.destroy()
G.root.update()

# main menu + settings also go through the clamped placement now
G.open_main_menu()
G.root.update()
menu = [w for w in G.root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
fits(menu, "main menu fits the screen")
stray = [w for w in walk(menu) if isinstance(w, ttk.Label)
         and str(w.cget('text')).strip() == 'Quick Start:']
sections = [w for w in walk(menu) if isinstance(w, ttk.Labelframe)
            and str(w.cget('text')) == 'Quick Start']
check("exactly one Quick Start section (was duplicated)",
      len(stray) == 0 and len(sections) == 1,
      f"{len(stray)} stray labels, {len(sections)} sections")
menu.destroy()
G.root.update()

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    raise SystemExit(1)
print("ALL UI CHECKS PASSED")
