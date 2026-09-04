"""Play many randomized sessions to shake out crashes."""
import tkinter as tk, importlib.util, random, sys, traceback
spec = importlib.util.spec_from_file_location("game", "mane_game.py")
game = importlib.util.module_from_spec(spec); spec.loader.exec_module(game)
game.TinyAdventureGUI.init_sounds = lambda self: None
root = tk.Tk()
G = game.TinyAdventureGUI.__new__(game.TinyAdventureGUI); G.__init__(root)
G.sound_enabled = False; G.music_enabled = False
G.log_delay_ms = 0   # the paced log uses after(), which needs a mainloop; keep lines synchronous
G.show_dice_roll = lambda *a, **k: None   # skip animations
# README ("Testing"): assign_rays() is modal (wait_window) and deadlocks headless
# runs - stub it to the auto-spread it offers as its default.
G.assign_rays = lambda *a, **k: G._spread_rays(*a, **k)

errors, turns = [], 0
for session in range(40):
    random.seed(session)
    cls = random.choice(list(game.CLASSES))
    lvl = random.randint(1, 5)
    try:
        G.quick_start_class(cls, level=lvl)
        # some sessions travel with a companion, so their whole path gets soaked
        if random.random() < 0.5:
            G.hire_companion(random.choice(list(game.COMPANIONS)), free=True)
        for _ in range(60):
            turns += 1
            if not G.in_combat:
                G.pending_enemies = G.make_enemy_pack(random.randint(1, 3), count=random.randint(1, 3))
                G.current_event = 'enemy'
                G.do_attack()
                continue
            action = random.choice(['quick', 'heavy', 'precise', 'spell', 'item', 'bonus', 'move', 'end'])
            if action == 'quick': G.do_quick_attack()
            elif action == 'heavy': G.do_heavy_attack()
            elif action == 'precise': G.do_precise_attack()
            elif action == 'move':
                random.choice([G.do_close_in, G.do_fall_back, G.do_take_cover])()
            elif action == 'spell' and G.known_spells:
                k = random.choice(G.known_spells)
                G.cast_spell(k, level=G.spell_catalog[k][2])
            elif action == 'item' and G.inventory:
                G.refresh_inventory()
                i = random.randrange(len(G._inventory_rows))
                G.inventory_list.selection_clear(0, tk.END); G.inventory_list.selection_set(i)
                G.do_use_item()
            elif action == 'bonus':
                if G.player_bonus_available: G.bonus_defend()
            else:
                G.end_turn()
                guard = 0
                while getattr(G, '_enemy_queue', None) and guard < 12:
                    G._enemy_turn_step(); guard += 1
                G._enemy_turn_step()
            if G.health <= 0:
                G.in_combat = False; G.enemies = []; G.health = G.max_health
            G.add_xp(random.randint(0, 60))
        # exercise save/load
        import json
        st = json.loads(json.dumps(G.game_state_dict()))
        G.apply_game_state(st)
    except Exception as e:
        traceback.print_exc(); errors.append(f"{cls} L{lvl}: {e}")

print(f"\n{turns} turns across 40 sessions, {len(errors)} errors")
if errors:
    for e in errors[:10]: print(" ", e)
    sys.exit(1)
print("SOAK CLEAN")
