# Tiny Adventure

A dungeon crawler in Python and tkinter. Roll up a character from one of twelve
classes, descend through procedurally generated floors, fight what lives there,
and try to get deep enough to meet something that has a name.

No dependencies beyond the standard library. Run it with:

```
python -m tiny_adventure
```

If tkinter is missing on Linux, install it with `sudo apt install python3-tk`.

---

## Contents

- [How the code is put together](#how-the-code-is-put-together)
- [The one rule](#the-one-rule)
- [File map](#file-map)
- [Playing the game](#playing-the-game)
- [Systems](#systems)
  - [Equipment and the four slots](#equipment-and-the-four-slots)
  - [Magic items](#magic-items)
  - [Spells and upcasting](#spells-and-upcasting)
  - [Hit dice and resting](#hit-dice-and-resting)
  - [Ability Score Improvements](#ability-score-improvements)
  - [Range, cover and the Move button](#range-cover-and-the-move-button)
  - [Enemy tactics and morale](#enemy-tactics-and-morale)
  - [Companions](#companions)
  - [Adaptive difficulty](#adaptive-difficulty)
  - [The narrator](#the-narrator)
  - [Bosses](#bosses)
  - [Starting fights and running from them](#starting-fights-and-running-from-them)
- [Where to edit what](#where-to-edit-what)
- [Testing](#testing)

---

## How the code is put together

The whole game is **one class**, `TinyAdventureGUI`, assembled in `app.py` from a
stack of mixins:

```python
class TinyAdventureGUI(UIMixin, CharacterMixin, CombatMixin, DungeonMixin,
                       ItemsMixin, SpellsMixin, ClassAbilityMixin,
                       PersistenceMixin, MenuMixin, AudioMixin):
```

Each mixin lives in its own file and owns one area of the game. Because they are
all folded into a single class, `self` is the entire game everywhere. Combat code
can call `self.gear_effects()` from `items.py` or `self.ability_mod()` from
`character.py` with no imports and no plumbing.

Every attribute is created in one of three places, in this order:

1. `app.py.__init__` — declares **every** attribute the game will ever use, so
   nothing is ever missing when a screen tries to read it
2. `build_ui()` — makes the widgets
3. `reset_game()` — sets everything to its new-character values

If you add state, add it to `app.py.__init__` as well as wherever you set it.
That is what stops `AttributeError` turning up three hours into someone's run.

## The one rule

**Never define the same method name in two mixins.**

Python resolves it silently by MRO order, the first one wins, and the other
simply never runs. There is no error, no warning, and the resulting bug can be
very hard to see. If you want to be sure:

```python
import ast, collections
owner = collections.defaultdict(list)
for m in ['ui','character','combat','dungeon','items','spells',
          'abilities','persistence','menus','audio']:
    for node in ast.parse(open(f'tiny_adventure/{m}.py').read()).body:
        if isinstance(node, ast.ClassDef):
            for f in node.body:
                if isinstance(f, ast.FunctionDef):
                    owner[f.name].append(m)
print({k: v for k, v in owner.items() if len(v) > 1} or "clean")
```

## File map

| File | What lives there |
|---|---|
| `app.py` | The class assembly, `__init__`, and the entry point. Start here. |
| `data.py` | **All the numbers and all the content.** Weapons, armour, magic items, spells, bosses, classes, loot tables. Edit this to change the game without touching logic. |
| `character.py` | Creation, levelling, ability scores, derived stats, spell slots, ASIs, death |
| `combat.py` | Enemies, bosses, the turn loop, enemy tactics, range and cover, damage, fleeing, rewards, the adaptive dial |
| `companions.py` | The hired ally: hiring, their turn brain, taking hits for you |
| `narrator.py` | The spoken narrator: key moments read aloud by the system voice |
| `dungeon.py` | Floor generation, the map window, rooms, traps, chests, skill checks |
| `items.py` | Inventory, the four equipment slots, magic item effects, the shop, loot |
| `spells.py` | The spellbook window and one branch per spell |
| `abilities.py` | Per-class abilities and the rest system |
| `ui.py` | The main window, the stat panel, the character sheet, the log |
| `menus.py` | Main menu, settings, save/load menu entries |
| `persistence.py` | Turning the game into JSON and back |
| `audio.py`, `audio_player.py` | Generated music and sound effects |
| `paths.py` | Where saves and settings go |

---

## Playing the game

Press **Explore** to open the dungeon map. Move with the arrow keys or WASD.

| Symbol | Room |
|---|---|
| `.` | empty |
| `E` | enemy — walking in starts the fight |
| `^` | trap |
| `#` | chest |
| `$` | treasure |
| `S` | shop |
| `C` | camp — the only place you can take a long rest |
| `?` | mystery |
| `v` | stairs down |
| `B` | **boss** — guards the stairs on every third floor |

On your turn, attacking spends your **action** but leaves your **bonus action**
free, and you also have one free **move** (the Move button: close in, fall back,
or take cover). Nothing on the enemies' side happens until you press **End
Turn**, so you can attack, then drink a potion, then decide.

---

## Systems

### Equipment and the four slots

Four slots: **weapon**, **armor**, **shield**, **trinket**.

Press **Gear** to see all four at once — what is in each one, what that item is
actually doing for you, a live summary of your AC, attack, damage, damage
reduction and crit range, and every alternative sitting in your bag. Swapping
during a fight costs your action.

The slots are defined in `data.py`:

```python
EQUIP_SLOTS = ('weapon', 'armor', 'shield', 'trinket')
SLOT_ATTR   = {'weapon': 'equipped_weapon', 'armor': 'equipped_armor',
               'shield': 'equipped_shield', 'trinket': 'equipped_trinket'}
```

`EQUIPPABLE` is derived at import from the weapon, armour, shield and magic item
tables, so anything you add to those becomes equippable automatically.

Taking a weapon off leaves you with `'unarmed strikes'` rather than an empty
slot — you always have fists, and that entry is a real row in `WEAPONS`.

### Magic items

34 of them, spread Uncommon (9), Rare (16), Very Rare (6), Legendary (3).

They are **pure data**. An entry looks like this:

```python
'dwarven warhammer': {
    'slot': 'weapon', 'rarity': 'Uncommon', 'price': 380,
    'dmg': 2, 'stat': {'strength': 1},
    'desc': 'Squat, brutal, older than the dungeon. +2 damage and +1 Strength.',
},
```

Everything equipped is summed by a single function, `gear_effects()` in
`items.py`. **Adding an item that uses an effect key already in the table needs
no code at all** — add the dict entry and it works, including in the shop, the
loot tables, the Gear screen and the character sheet.

The effect keys currently understood:

| Key | Effect |
|---|---|
| `ac` | flat armour class |
| `atk` | attack bonus |
| `dmg` | damage bonus |
| `spell_atk` | spell attack bonus |
| `stat` | dict of ability score bonuses |
| `max_hp` | extra maximum health |
| `bonus_damage` / `damage_type` | extra dice of a named damage type on a hit |
| `crit_range` | crit on this number or better (a sword of sharpness crits on 19) |
| `dr` | damage reduction, taken off every hit |
| `regen` | health regained at the start of each combat round |
| `check_bonus` | bonus to skill checks |
| `slot_bonus` | extra spell slots |
| `light` | lights the floor around you |
| `flee_bonus` | bonus when running away |

To add a genuinely new *kind* of effect, add the key to `gear_effects()` and read
it wherever it applies.

### Subclasses

Every class walks one of two **paths** — D&D-style archetypes (Champion or
Battle Master for a Fighter, Life or War Domain for a Cleric, a Draconic
Bloodline or Wild Magic for a Sorcerer, and so on). You pick yours at character
creation; Quick Start picks one at random unless you choose.

Like magic items, subclasses are **pure data** — `SUBCLASSES` in `data.py`,
using the very same effect keys, because `gear_effects()` folds them in. A
Champion's crit-on-19 and an Abjurer's +1 AC flow through the exact plumbing a
sword of sharpness and a ring of protection already use, so adding a subclass
needs no code. One extra key exists just for them: `max_hp_per_level`.

Your path shows in the character panel, on the sheet, and survives saves;
pre-subclass saves load fine with no path.

### Spells and upcasting

**96 spells**: 19 cantrips, 23 first level, 16 second, 15 third, 11 fourth, 12
fifth. Mixed classic and invented — Fireball and Counterspell sit next to Soul
Harvest and Wall of Force.

Casting takes the **slot level**, not the spell level:

```python
def cast_spell(self, spell_key, level=1, from_scroll=False):
    upcast = level - spell_level
```

Every spell that scales reads `upcast`. Fireball rolls `8 + upcast` dice; Magic
Missile fires `3 + upcast` darts. The spellbook draws **one button per slot you
could actually spend**, labelled `Cast (L3)` or `Upcast L5`, with a note on what
the bigger slot buys — so upcasting is one click and never guesswork.

Cantrips cost nothing and gain dice at levels 5, 11 and 17 via `cantrip_dice()`.

Order matters inside `cast_spell`: every check that could refuse the spell runs
*before* the slot is spent, so a refused spell never costs you anything. Scrolls
pass `from_scroll=True`, which skips the class check, the slot cost and the
action cost, and refunds the scroll if the spell declines to fire.

### Hit dice and resting

Your hit dice are your real healing budget between camps, so the game shows them
in three places: the character panel, the Stats sheet, and the rest dialog
itself.

- **Short rest** — spends one hit die, heals `1d(hit die) + CON`. Risky: something
  may find you, and if it does you cannot rest again until you deal with it.
- **Long rest** — camps only. Restores health, **all hit dice**, every spell slot
  and all class resources, and clears poison and temporary HP.

You gain a hit die every level, and `hit_dice_max` tracks your level exactly.

### Ability Score Improvements

At levels **4, 8, 12, 16 and 19** you get an ASI: **+2 to one ability, or +1 to
two**, capped at 20.

The dialog opens automatically shortly after you level. It has a *Decide Later*
button, and unspent improvements are remembered — the character panel shows
`ABILITY SCORE IMPROVEMENT WAITING`, they survive a save and reload, and the
dialog reopens if you are owed more than one.

ASIs raise your **base** score. Because gear also grants ability bonuses,
everything that matters reads `ability_score(name)` (base + gear) and
`ability_mod(name)` rather than the raw attribute. If you write new code that
cares about an ability score, use those.

You can start a new character at up to level 10, so the deeper spells and the
ASIs are reachable without a full climb.

### Range, cover and the Move button

Every enemy is either **near** (in your face) or **far** (hanging back), shown
as `at range` on its card. Skirmishers — kobolds, cultists, harpies,
elementals, wyrms (`RANGED_ENEMIES` in `data.py`) — open the fight far and
shoot from there.

The rule that keeps this friction-free: **a melee swing at a far target simply
closes the distance first**, spending your free move for the round. Nothing
ever refuses. If your move is already gone, you can still lunge at **-4**.
Ranged weapons (`RANGED`) and all spells reach any distance; spells arc right
over cover, which is the casters' answer to entrenched skirmishers.

You get **one move per round**, and the **Move** button spends it on purpose:

- **Close In** — engage a far target without attacking yet.
- **Fall Back** — push everything to range. Everyone you disengage from gets
  one parting swipe at -2 for half damage — *unless you are a Rogue*, whose
  cunning footwork is exactly for this. It also strips pack tactics and forces
  the melee enemies to spend their turns closing again.
- **Take Cover** — about 60% of fights (`OBSTACLE_CHANCE`) spawn an obstacle:
  a toppled pillar, a barricade, an overturned cart. Behind it you get
  **+2 AC against ranged attacks** (`COVER_AC`) and **half damage from a
  boss's breath or quake** — though the blast has a 40% chance of smashing
  your cover to bits. Swinging a melee weapon or closing in steps you out.

Enemies use the same rules against you: a hurt skirmisher will fall back
behind the very same obstacle, and your arrows will start thudding into it.

### Enemy tactics and morale

Ordinary enemies think for themselves now. Their whole brain is one readable
method — `enemy_take_turn` in `combat.py` — a priority list, top to bottom:

1. **Morale** — a survivor below 35% HP whose pack has lost half its number
   has a 30% chance per turn to simply bolt (`MORALE_HP_FRAC`,
   `MORALE_CHANCE`). You get a little XP for breaking them; they drop
   nothing, and their card reads *fled*. The mindless — skeletons, zombies,
   golems, the rest of `FEARLESS_ENEMIES` — and all bosses never run.
2. **Kite** — a hurt skirmisher you have closed with opens the distance again
   (once per fight), ducking into cover if the room has any. Repositioning
   costs it its attacks, so kiting buys it a round rather than winning fights.
3. **Rush** — a melee straggler still at range closes in and *still* swings:
   closing is free for them too.
4. **Pack tactics** — each other near melee ally makes an enemy bolder:
   +1 to hit, capped at +2 (`PACK_TACTICS_CAP`), announced once. Killing into
   the pack — or Falling Back — strips it.

### Companions

Any shop will hire you **one** ally (the bar under Buy/Sell). Four archetypes,
pure data in `COMPANIONS`:

| Who | What they do |
|---|---|
| **Sellsword** | Draws 55% of attacks aimed at you, hits with a d8 |
| **Archer** | Focuses the weakest enemy from wherever they stand |
| **Apprentice** | Snaps motes of fire — resistances and vulnerabilities apply |
| **Field Medic** | Patches you up when you are below 60%, jabs otherwise |

They act automatically after you End Turn and before the enemies move, scale
with **your** level (no XP to manage), show on the combat canvas and in the
status strip, and survive saves. Enemies treat them as real: every swing may
be intercepted (`companion_should_intercept`), resolved against the
companion's own AC and HP. At 0 HP they are **gone for good** — hire another
at the next shop, for a price that climbs with the floor.

### Adaptive difficulty

A quiet dial (`adaptive_mult`, bounded 0.85–1.15) that listens to your last
eight fights — HP lost, deaths, ten-round slogs — and drifts a step at a time
(`ADAPTIVE_*` in `data.py`). Struggle, and pack HP budgets thin out while the
drop chance rises; cruise, and they firm back up. It nudges rather than
rescues, says nothing in the log, and can be turned off in **Settings**. The
multiplier is saved with the character. `balance_probe.py` pins it off so the
probe always measures the raw dials.

### The narrator

A voice speaks the headlines so you do not have to read every log line
mid-fight. It is deliberately terse and deliberately picky:

- **one damage summary per round** — "You took 8 damage. 21 health left."
  (with a "Careful!" when you drop below 30%) — never a line per hit
- kills ("Goblin down."), routs, and "Victory!" when the room is cleared
- a boss winding up its big move — "Big attack coming. Take cover!"
- level ups, your companion going down, your own death
- traps and poison outside combat

**No new dependencies.** Speech comes from whatever the OS already has:
Windows' built-in SAPI voice (driven through one hidden persistent PowerShell
worker), macOS `say`, or Linux `espeak` if installed — and it silently does
nothing on machines with none of those. Phrases queue two deep and the oldest
is *dropped*, not stacked, so the voice never lags behind the action.

Toggle it in **Settings → Narrator** (persisted). It also obeys the master
*Enable Sound Effects* switch, which is why the headless test harnesses never
spawn a voice. What it says lives in the small `narrate(...)` calls in
`combat.py`, `character.py` and `companions.py`; how it speaks lives in
`narrator.py`.

### Bosses

Every **third** floor (`BOSS_EVERY = 3`) the far room is a boss instead of the
stairs. **Beating it is what opens the way down.**

Six bosses across three tiers, which one you meet depending on depth, with their
statistics scaling on top of that — the same boss on floor 12 is a very different
proposition from floor 3. They:

- attack several times per round, exactly as their statblock says (Size Up
  the Enemy tells the truth)
- have resistances and vulnerabilities worth knowing about
- bring minions
- use a signature move on a three-round cooldown: `rally`, `drain`, `web`,
  `curse`, `quake` or `breath`
- **telegraph that move one round early** ("The wyrm inhales, and keeps
  inhaling...") — `TELEGRAPHS` in `data.py` — so Taking Cover (which halves
  `breath` and `quake`) or Falling Back in time is a real decision
- **enrage below half health** — +2 to attack and an extra attack each round
- get +4 on saving throws, so save-or-suck spells are not a shortcut
- drop scaled gold and XP plus a guaranteed magic item of an appropriate rarity

Use **Bonus Action → Size Up the Enemy** to read a boss's AC, health, attacks and
resistances before committing to a plan.

Adding one is a `BOSSES` entry in `data.py` plus, if it needs a new signature
move, one branch in `boss_special()`.

### Starting fights and running from them

Walking into an enemy room **starts the fight immediately**. There is no "press
Attack to begin". You get a surprise check first — a Wisdom check against
`9 + floor` — and losing it hands the enemies the opening round while you are
still drawing your weapon. Bosses never surprise you; the door just shuts.

The **Flee** button is available every round of every fight. It is a Dexterity
check against:

```python
flee_dc = 9 + floor + 2 * (enemies - 1) + (5 if boss else 0)
```

modified by difficulty, your gear's `flee_bonus`, a smoke bomb (+6) and haste
(+4), plus **+3 when everything still standing is at range** — nothing within
arm's reach means a head start. Misty Step and Dimension Door make the next
escape automatic.

Succeed and you fall back to the room you came from, with the enemies still
sitting where you left them. Fail and you lose the round.

---

## Where to edit what

Almost all balance and content changes are `data.py` only:

| Want to change | Edit |
|---|---|
| A weapon's damage or price | `WEAPONS` |
| Armour or shields | `ARMOR`, `SHIELDS` |
| Add a magic item | `MAGIC_ITEMS` (no code needed for existing effect keys) |
| Add or tune a subclass | `SUBCLASSES` (pure data, the same effect keys as magic items) |
| Add or rebalance a spell | `SPELL_CATALOG` + a branch in `spells.py`; `SPELL_UPCAST` for the note |
| Who can learn what | `CLASS_SPELLS` |
| Class starting kit or stats | `CLASSES` |
| Add a boss | `BOSSES` (+ `boss_special()` for a new move) |
| How often bosses appear | `BOSS_EVERY` |
| Which enemies shoot, and their flavour | `RANGED_ENEMIES`, `RANGED_VERBS` |
| Who never flees | `FEARLESS_ENEMIES` |
| Cover strength, obstacle odds and props | `COVER_AC`, `OBSTACLE_CHANCE`, `OBSTACLES` |
| Morale and pack tactics | `MORALE_HP_FRAC`, `MORALE_CHANCE`, `PACK_TACTICS_CAP` |
| Boss warnings | `TELEGRAPHS` |
| Companion archetypes and hire prices | `COMPANIONS`, `COMPANION_HIRE_PER_FLOOR` |
| Adaptive difficulty bounds and pace | `ADAPTIVE_MIN/MAX/STEP/WINDOW` |
| How ordinary enemies think | `enemy_take_turn` in `combat.py` (logic, not data) |
| What the narrator says, and when | the `narrate(...)` calls in `combat.py` / `character.py` |
| How the narrator speaks | `narrator.py` |
| When ASIs happen, or the cap | `ASI_LEVELS`, `ABILITY_CAP` |
| Consumables and prices | `ITEM_INFO`, `ITEM_PRICES` |
| What drops | `COMMON_LOOT`, `DEEP_LOOT`, `SCROLLS`, `VALUABLES` |
| Difficulty | `DIFFICULTIES` |
| Overall pacing: player HP, XP curve, pack and boss HP growth | `PLAYER_HP_BASE`, `XP_GROWTH`, `PACK_HP_BUDGET`, `PACK_HP_PER_FLOOR`, `BOSS_HP_SCALE` |

Derived tables — `EQUIPPABLE`, `MAGIC_BY_RARITY`, `MUNDANE_WEAPONS`,
`CONSUMABLES` — are built at import from the tables above. Add to the source
table and they update themselves.

---

## Testing

There is no display in most automated environments, so the test harness builds a
real `Tk` root, withdraws it, and stubs out audio and the blocking modal dialogs.
The suites: `test_fixes.py` (core rules and the action economy),
`test_subclasses.py`, `test_ui_fixes.py`, `test_dialogs.py`,
`test_tactics.py` (range, cover, the Move options, enemy AI, morale,
telegraphs, companions, adaptive difficulty), plus `soak.py` for randomized
crash-hunting and `balance_probe.py` for pacing numbers.
Two things are worth knowing if you write more tests:

- **Enemy turns chain through `root.after()`.** A test must pump the event loop
  (`root.update()` in a short timed loop) or only the first enemy will act.
- **`assign_rays()` is modal** (`wait_window`). Stub it to `_spread_rays()`
  headlessly or it deadlocks.

Run the game under a virtual display with:

```
xvfb-run -a python -m tiny_adventure
```

A few behaviours look like bugs and are not, so please don't "fix" them:

- unequipping a weapon leaves `'unarmed strikes'`, not `None`
- `roll_loot()` returns **one item name**, not a list
- `damage_player()` deliberately does not kill you — it returns the damage that
  landed and leaves death to the caller, so the caller can finish its own logging
  first. Every current caller handles it; new ones must too.
- a short rest interrupted by an ambush correctly blocks resting again
- unarmoured AC is `10 + DEX`, which is legitimately **below 10** for a caster
  with a poor Dexterity
