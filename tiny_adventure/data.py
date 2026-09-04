"""Static game data - all the numbers and tables, in one place.

THIS IS THE FILE TO EDIT FOR BALANCE AND CONTENT. Nothing here has any
behaviour attached; it is pure data that the rest of the game reads. You can
change any value in this file without touching game logic.

What lives here, in order:

    WEAPONS              damage, accuracy and price of every weapon
    FINESSE              which weapons may use DEX instead of STR
    ARMOR                AC bonus and price of every armour piece
    SHIELDS              AC bonus and price of every shield
    MAGIC_ITEMS          every magic item and the effects it grants
    EQUIP_SLOTS          the four things you can be wearing at once
    CLASSES              the 12 playable classes and their starting kit
    DIFFICULTIES         Easy/Normal/Hard multipliers
    CLASS_SPELLS         which spells each class is allowed to learn
    OUT_OF_COMBAT_SPELLS which spells work with no enemies around
    CLASS_STAT_PRIORITY  where rolled scores go for each class
    STARTING_KIT         items every character begins with
    ITEM_INFO            inventory descriptions
    ITEM_PRICES          what the shop charges for non-gear items
    SCROLLS              which spell each scroll casts
    VALUABLES            loot that exists purely to be sold
    COMMON_LOOT          the random drop pool
    SPELL_CATALOG        every spell: name, description, level, action cost
    SPELL_UPCAST         what each spell gains from a higher slot
    BOSSES               the floor bosses and their special moves
    ASI_LEVELS           which levels grant an Ability Score Improvement

COMMON EDITS

    Make a weapon hit harder ............ WEAPONS, first number
    Make the game easier ................ DIFFICULTIES
    Give a class a different spell ...... CLASS_SPELLS
    Change what you start with .......... STARTING_KIT
    Add a brand new spell ............... SPELL_CATALOG *and* CLASS_SPELLS,
                                          then add its effect in spells.py
    Add a magic item .................... MAGIC_ITEMS (plus WEAPONS/ARMOR/
                                          SHIELDS if it is a weapon or armour)
    Change a boss ....................... BOSSES

A warning about spells: adding an entry to SPELL_CATALOG only makes the spell
*exist*. Its actual effect is a branch in cast_spell() over in spells.py. A
spell with no branch there falls through to a generic damage effect.

A note on edition: this game is D&D-*flavoured*, not D&D-*compliant*. Plenty
of what follows is invented, renamed or rebalanced to suit a small dungeon
crawler. Treat the tables as a starting point, not as scripture.
"""

# -----------------------------------------------------------------------------


# --- Weapons -----------------------------------------------------------------
# name: (damage_die, attack_modifier, price_in_gold)
#
#   damage_die       roll 1dN for damage. 6 means d6. Bigger = hits harder.
#   attack_modifier  added to your roll to hit. +1 is accurate, -1 is clumsy.
#   price            what the shop charges.
#
# The trade-off across the table is accuracy against damage: the greataxe hits
# for a d12 but at -1 to hit, the dagger only d4 but at +1.
#
# Magic weapons live in this table too so that their damage die and price work
# everywhere. Their *extra* powers are described in MAGIC_ITEMS further down,
# and anything listed there is excluded from ordinary shop and chest loot.
#
# To add a weapon: add a line here, and it can then be sold in the shop or set
# as a class's starting weapon in CLASSES below.
WEAPONS = {
    # --- simple weapons ---
    'unarmed strikes': (4, 0, 0),
    'club':          (4, 0, 2),
    'sling':         (4, 0, 3),
    'dagger':        (4, 1, 8),
    'whip':          (4, 1, 12),
    'sickle':        (4, 1, 10),
    'handaxe':       (6, 0, 12),
    'quarterstaff':  (6, 0, 15),
    'spear':         (6, 0, 14),
    'mace':          (6, 0, 25),
    'shortsword':    (6, 0, 25),
    'shortbow':      (6, 1, 40),
    'scimitar':      (6, 1, 30),
    'light crossbow': (8, 0, 35),
    # --- martial weapons ---
    'trident':       (8, 0, 40),
    'morningstar':   (8, 0, 45),
    'rapier':        (8, 0, 45),
    'battleaxe':     (8, 0, 50),
    'longsword':     (8, 0, 50),
    'warhammer':     (8, 0, 55),
    'longbow':       (8, 1, 70),
    'glaive':        (10, -1, 65),
    'halberd':       (10, -1, 65),
    'heavy crossbow': (10, -1, 75),
    'pike':          (10, -1, 60),
    'greataxe':      (12, -1, 80),
    'maul':          (12, -1, 85),
    'greatsword':    (12, -1, 90),
    # --- magic weapons (see MAGIC_ITEMS for what they actually do) ---
    'silvered dagger':    (4, 2, 120),
    'sword of the vigil': (8, 1, 320),
    'dwarven warhammer':  (8, 1, 380),
    'elven longbow':      (8, 2, 450),
    'flametongue':        (8, 1, 900),
    'frostbrand':         (8, 1, 900),
    'stormcaller spear':  (6, 2, 850),
    'venomfang blade':    (6, 2, 700),
    'sunblade':           (8, 2, 1100),
    'sword of sharpness': (10, 2, 1400),
    'earthshaker maul':   (12, 0, 1250),
    'staff of the magi':  (6, 1, 1500),
}

# Finesse weapons use STR or DEX for damage, whichever is better (see
# update_derived_stats in character.py). This is what makes light weapons
# worth using for a Rogue. Every name here must also exist in WEAPONS above.
FINESSE = {
    'unarmed strikes', 'dagger', 'whip', 'sickle', 'shortsword', 'scimitar',
    'rapier', 'shortbow', 'longbow', 'light crossbow', 'sling',
    'silvered dagger', 'venomfang blade', 'sunblade', 'elven longbow',
    'stormcaller spear', 'sword of the vigil',
}

# Ranged weapons - flagged only so the log can describe them properly and so
# a few items (bracers of archery) know what to boost.
RANGED = {'shortbow', 'longbow', 'light crossbow', 'heavy crossbow', 'sling',
          'elven longbow'}

# --- Armour ------------------------------------------------------------------
# name: (ac_bonus, price_in_gold)
#
# ac_bonus is added straight to your Armour Class - the number enemies must
# beat on a d20 to hit you. Your AC is 10 + DEX modifier + this + shield +
# trinkets + any spells. Every point is a real defensive gain, so keep these
# small.
ARMOR = {
    'padded armor':     (1, 8),
    'leather armor':    (1, 15),
    'hide armor':       (2, 20),
    'ring mail':        (2, 30),
    'studded leather':  (2, 45),
    'scale mail':       (3, 50),
    'chain shirt':      (3, 55),
    'chain mail':       (3, 60),
    'breastplate':      (4, 90),
    'half plate':       (4, 110),
    'splint armor':     (5, 130),
    'plate armor':      (5, 140),
    # --- magic armour ---
    'elven chain':      (3, 400),
    'mithral plate':    (5, 800),
    'dragonscale mail': (4, 950),
    'armor of the bulwark': (5, 1100),
}

# --- Shields -----------------------------------------------------------------
# A shield occupies its own equipment slot, so you can carry one alongside any
# weapon and armour. name: (ac_bonus, price_in_gold)
SHIELDS = {
    'buckler':        (1, 10),
    'wooden shield':  (1, 12),
    'iron shield':    (2, 30),
    'tower shield':   (3, 75),
    # --- magic shields ---
    'shield of the sentinel': (2, 350),
    'aegis of warding':       (3, 900),
}

# --- Equipment slots ---------------------------------------------------------
# The four things you can have equipped at once. Each maps to an attribute on
# the character (equipped_weapon, equipped_armor, equipped_shield,
# equipped_trinket) and to the table that describes what can go there.
EQUIP_SLOTS = ('weapon', 'armor', 'shield', 'trinket')

SLOT_ATTR = {
    'weapon':  'equipped_weapon',
    'armor':   'equipped_armor',
    'shield':  'equipped_shield',
    'trinket': 'equipped_trinket',
}

# --- Magic items -------------------------------------------------------------
# name: dict of properties. Every key is optional except slot and desc.
#
#   slot          'weapon', 'armor', 'shield' or 'trinket'
#   rarity        Uncommon / Rare / Very Rare / Legendary - drives loot tables
#   price         gold value, for shops and for selling
#   desc          the line shown in your inventory
#
# THE EFFECTS - all of these are read by update_derived_stats in character.py
# and by perform_combat_attack in combat.py. Adding a new key here does
# nothing on its own; it needs reading somewhere.
#
#   ac            flat bonus to Armour Class
#   atk           flat bonus to weapon attack rolls
#   dmg           flat bonus to weapon damage
#   spell_atk     flat bonus to spell attack rolls and spell save DC
#   stat          {'strength': 2} - added to that ability score
#   max_hp        flat bonus to maximum HP
#   bonus_damage  (count, die) extra damage dice on every weapon hit
#   damage_type   flavour text for that bonus damage
#   crit_range    19 means you crit on a 19 or a 20
#   dr            flat damage reduction on every hit you take
#   regen         HP regained at the start of each of your combat rounds
#   check_bonus   flat bonus to every ability check (traps, locks, leaping)
#   slot_bonus    {1: 1} - extra spell slots of that level
#   light         True if it lights rooms like a permanent torch
#   flee_bonus    flat bonus to your roll when running from a fight
#
# Weapons, armour and shields listed here must ALSO appear in WEAPONS, ARMOR
# or SHIELDS above - that is where their die/AC/price come from.
MAGIC_ITEMS = {
    # --- weapons ---
    'silvered dagger': dict(
        slot='weapon', rarity='Uncommon', price=120, dmg=1,
        desc='A blade chased with pure silver. +1 damage, and it bites undead things especially hard.'),
    'sword of the vigil': dict(
        slot='weapon', rarity='Uncommon', price=320, atk=1, dmg=1,
        desc='A watchman\'s longsword that never dulls. +1 to hit and +1 damage.'),
    'dwarven warhammer': dict(
        slot='weapon', rarity='Uncommon', price=380, dmg=2, stat={'strength': 1},
        desc='Squat, brutal, older than the dungeon. +2 damage and +1 Strength.'),
    'elven longbow': dict(
        slot='weapon', rarity='Rare', price=450, atk=2, dmg=1,
        desc='So light it feels unstrung. +2 to hit, +1 damage.'),
    'flametongue': dict(
        slot='weapon', rarity='Rare', price=900, atk=1,
        bonus_damage=(2, 6), damage_type='fire', light=True,
        desc='The blade sheathes itself in flame. +1 to hit and +2d6 fire damage on every hit. Lights the room.'),
    'frostbrand': dict(
        slot='weapon', rarity='Rare', price=900, atk=1, dr=2,
        bonus_damage=(1, 8), damage_type='cold',
        desc='Rimed with frost that never melts. +1 to hit, +1d8 cold damage, and you shrug off 2 damage from every blow.'),
    'stormcaller spear': dict(
        slot='weapon', rarity='Rare', price=850, atk=2,
        bonus_damage=(1, 8), damage_type='lightning',
        desc='Thunder rolls somewhere far off whenever you throw it. +2 to hit, +1d8 lightning damage.'),
    'venomfang blade': dict(
        slot='weapon', rarity='Rare', price=700, atk=2,
        bonus_damage=(2, 4), damage_type='poison',
        desc='A serrated fang set in a hilt. +2 to hit and +2d4 poison damage.'),
    'sunblade': dict(
        slot='weapon', rarity='Very Rare', price=1100, atk=2, light=True,
        bonus_damage=(2, 8), damage_type='radiant',
        desc='A hilt that blooms into a blade of pure daylight. +2 to hit, +2d8 radiant damage, and it lights every room.'),
    'sword of sharpness': dict(
        slot='weapon', rarity='Very Rare', price=1400, atk=2, crit_range=19,
        desc='It parts armour like wet paper. +2 to hit, and you score a critical hit on a 19 or a 20.'),
    'earthshaker maul': dict(
        slot='weapon', rarity='Very Rare', price=1250, dmg=3, stat={'strength': 2},
        bonus_damage=(1, 10), damage_type='thunder',
        desc='Two-handed, ruinous, and it hums. +3 damage, +2 Strength, +1d10 thunder damage.'),
    'staff of the magi': dict(
        slot='weapon', rarity='Legendary', price=1500, spell_atk=2,
        slot_bonus={1: 1, 2: 1, 3: 1},
        desc='Knotted darkwood crowned with a caged star. +2 to spell attacks and save DC, and one extra slot of levels 1, 2 and 3.'),

    # --- armour ---
    'elven chain': dict(
        slot='armor', rarity='Rare', price=400, ac=1, check_bonus=1,
        desc='Links so fine they whisper. +1 AC on top of its armour, and it never hinders you (+1 to checks).'),
    'mithral plate': dict(
        slot='armor', rarity='Rare', price=800, ac=1, dr=1,
        desc='Plate that weighs as much as a coat. +1 AC and 1 point of damage reduction.'),
    'dragonscale mail': dict(
        slot='armor', rarity='Very Rare', price=950, ac=2, dr=2, max_hp=10,
        desc='Overlapping scales, still warm. +2 AC, 2 damage reduction, +10 max HP.'),
    'armor of the bulwark': dict(
        slot='armor', rarity='Legendary', price=1100, ac=2, dr=3, max_hp=15,
        desc='Siege armour worn by something that never retreated. +2 AC, 3 damage reduction, +15 max HP.'),

    # --- shields ---
    'shield of the sentinel': dict(
        slot='shield', rarity='Uncommon', price=350, ac=1,
        desc='It leans toward incoming blows on its own. +1 AC on top of the shield itself.'),
    'aegis of warding': dict(
        slot='shield', rarity='Very Rare', price=900, ac=2, dr=2,
        desc='A ward flares whenever something swings at you. +2 AC and 2 damage reduction.'),

    # --- trinkets (rings, cloaks, amulets, boots, belts, gloves) ---
    'ring of protection': dict(
        slot='trinket', rarity='Uncommon', price=300, ac=1,
        desc='A plain iron band that is never quite where a blade lands. +1 AC.'),
    'ring of the warrior': dict(
        slot='trinket', rarity='Uncommon', price=340, atk=1, dmg=1,
        desc='Worn smooth by generations of sword hands. +1 to hit and +1 damage.'),
    'amulet of health': dict(
        slot='trinket', rarity='Rare', price=500, stat={'constitution': 2}, max_hp=10,
        desc='A heavy jade drop that steadies your pulse. +2 Constitution and +10 max HP.'),
    'cloak of elvenkind': dict(
        slot='trinket', rarity='Uncommon', price=380, check_bonus=2, flee_bonus=4,
        desc='It takes on the colour of whatever is behind you. +2 to ability checks and +4 when fleeing a fight.'),
    'boots of speed': dict(
        slot='trinket', rarity='Rare', price=520, ac=1, flee_bonus=6,
        desc='Your steps land a half-second before you take them. +1 AC and +6 when fleeing a fight.'),
    'gauntlets of ogre power': dict(
        slot='trinket', rarity='Rare', price=560, stat={'strength': 3},
        desc='Enormous, and they shrink to fit. +3 Strength.'),
    'headband of intellect': dict(
        slot='trinket', rarity='Rare', price=560, stat={'intelligence': 3},
        desc='A cold circlet that finishes your sentences. +3 Intelligence.'),
    'periapt of wisdom': dict(
        slot='trinket', rarity='Rare', price=560, stat={'wisdom': 3},
        desc='A pale stone that makes the obvious obvious. +3 Wisdom.'),
    'circlet of glamour': dict(
        slot='trinket', rarity='Rare', price=560, stat={'charisma': 3},
        desc='People agree with you slightly too readily. +3 Charisma.'),
    'bracers of archery': dict(
        slot='trinket', rarity='Uncommon', price=320, atk=1, dmg=2,
        desc='Tight leather braced with horn. +1 to hit and +2 damage (bows especially).'),
    'ring of regeneration': dict(
        slot='trinket', rarity='Very Rare', price=1000, regen=3,
        desc='Small wounds close while you watch. Regain 3 HP at the start of each of your combat rounds.'),
    'belt of the bulwark': dict(
        slot='trinket', rarity='Rare', price=600, dr=2, max_hp=8,
        desc='A wide banded belt that takes the impact for you. 2 damage reduction and +8 max HP.'),
    'wand of the arcanist': dict(
        slot='trinket', rarity='Rare', price=650, spell_atk=2,
        desc='Yew, cracked, faintly warm. +2 to spell attacks and to your spell save DC.'),
    'pearl of power': dict(
        slot='trinket', rarity='Rare', price=700, slot_bonus={1: 1, 2: 1},
        desc='A milky pearl that refills itself overnight. One extra spell slot of level 1 and of level 2.'),
    'luckstone': dict(
        slot='trinket', rarity='Uncommon', price=340, check_bonus=2, atk=1,
        desc='A river pebble with a hole through it. +2 to ability checks and +1 to hit.'),
    'crown of the deep': dict(
        slot='trinket', rarity='Legendary', price=1600,
        ac=2, spell_atk=2, max_hp=20, regen=2,
        desc='Worn by whatever built the lowest floor. +2 AC, +2 spell attack and DC, +20 max HP, and 2 HP regeneration each round.'),
}

# --- Classes -----------------------------------------------------------------
# Each entry describes how a character of that class starts out:
#
#   hit_die      size of die spent to heal on a short rest (d12 Barbarian is tough)
#   stat_bonus   added to those abilities at creation, on top of rolled scores
#   weapon       what they start wielding - must be a name from WEAPONS
#   armor        what they start wearing - a name from ARMOR, or None
#   shield       what they start carrying - a name from SHIELDS, or None
#   caster       how spell slots are granted:
#                  'full' - Wizard-style table, the most slots (see compute_slots)
#                  'half' - Paladin/Ranger, slower and fewer
#                  'pact' - Warlock, few slots but always at top level
#                  None   - no spellcasting at all
#   cast_stat    the ability that powers spell attacks and save DCs
#   spells       signature spells they always begin knowing
#   extra_items  added to the bag on top of STARTING_KIT
#
# To add a class: add an entry here, then give it a spell list in CLASS_SPELLS
# and an ability order in CLASS_STAT_PRIORITY - both further down this file.
# Any class-specific powers (rage, sneak attack) are coded in abilities.py.
CLASSES = {
    'Barbarian': dict(hit_die=12, stat_bonus={'strength': 2, 'constitution': 1}, weapon='greataxe', armor=None,
                      shield=None, caster=None, cast_stat=None, spells=[],
                      extra_items=['potion', 'whetstone']),
    'Bard':      dict(hit_die=8, stat_bonus={'charisma': 2, 'dexterity': 1}, weapon='rapier', armor='leather armor',
                      shield=None, caster='full', cast_stat='charisma',
                      spells=['prestidigitation', 'cure_wounds', 'sleep'],
                      extra_items=['lucky coin']),
    'Cleric':    dict(hit_die=8, stat_bonus={'wisdom': 2, 'strength': 1}, weapon='mace', armor='chain mail',
                      shield='wooden shield', caster='full', cast_stat='wisdom',
                      spells=['sacred_flame', 'cure_wounds', 'spiritual_weapon', 'hold_person'],
                      extra_items=['holy water']),
    'Druid':     dict(hit_die=8, stat_bonus={'wisdom': 2, 'constitution': 1}, weapon='quarterstaff', armor='leather armor',
                      shield=None, caster='full', cast_stat='wisdom',
                      spells=['thorn_whip', 'cure_wounds', 'faerie_fire'],
                      extra_items=['healing herbs', 'healing herbs']),
    'Fighter':   dict(hit_die=10, stat_bonus={'strength': 2, 'constitution': 1}, weapon='longsword', armor='chain mail',
                      shield='iron shield', caster=None, cast_stat=None, spells=[],
                      extra_items=['rope', 'whetstone']),
    'Monk':      dict(hit_die=8, stat_bonus={'dexterity': 2, 'wisdom': 1}, weapon='unarmed strikes', armor=None,
                      shield=None, caster=None, cast_stat=None, spells=[],
                      extra_items=['potion', 'ration']),
    'Paladin':   dict(hit_die=10, stat_bonus={'strength': 2, 'charisma': 1}, weapon='longsword', armor='chain mail',
                      shield='iron shield', caster='half', cast_stat='charisma',
                      spells=['cure_wounds'], extra_items=['holy water']),
    'Ranger':    dict(hit_die=10, stat_bonus={'dexterity': 2, 'wisdom': 1}, weapon='shortbow', armor='leather armor',
                      shield=None, caster='half', cast_stat='wisdom',
                      spells=['cure_wounds'], extra_items=['rope', 'ration']),
    'Rogue':     dict(hit_die=8, stat_bonus={'dexterity': 2, 'intelligence': 1}, weapon='shortsword', armor='leather armor',
                      shield=None, caster=None, cast_stat=None, spells=[],
                      extra_items=['torch', 'thieves tools', 'smoke bomb']),
    'Sorcerer':  dict(hit_die=6, stat_bonus={'charisma': 2, 'constitution': 1}, weapon='dagger', armor=None,
                      shield=None, caster='full', cast_stat='charisma',
                      spells=['ray_of_frost', 'burning_hands', 'magic_missile', 'mage_armor'],
                      extra_items=['potion']),
    'Warlock':   dict(hit_die=8, stat_bonus={'charisma': 2, 'constitution': 1}, weapon='dagger', armor='leather armor',
                      shield=None, caster='pact', cast_stat='charisma',
                      spells=['eldritch_blast', 'hold_person'],
                      extra_items=['potion']),
    'Wizard':    dict(hit_die=6, stat_bonus={'intelligence': 2, 'dexterity': 1}, weapon='quarterstaff', armor=None,
                      shield=None, caster='full', cast_stat='intelligence',
                      spells=['ray_of_frost', 'magic_missile', 'mage_armor'],
                      extra_items=['potion', 'scroll of magic missile']),
}

# --- Difficulty ---------------------------------------------------------------
# Multipliers applied to every enemy and reward. Chosen in Settings.
#
#   enemy_hp   scales enemy health (0.75 = enemies have 25% less)
#   enemy_atk  added to every enemy attack roll (flat, not a multiplier)
#   gold/xp    scale rewards
#   flee       added to your roll when you try to run from a fight
#
# This is the first knob to reach for if the game feels too hard or too easy.
DIFFICULTIES = {
    'Easy':   dict(enemy_hp=0.75, enemy_atk=-1, gold=1.25, xp=1.0, flee=3),
    'Normal': dict(enemy_hp=1.0, enemy_atk=0, gold=1.0, xp=1.0, flee=0),
    'Hard':   dict(enemy_hp=1.35, enemy_atk=1, gold=1.0, xp=1.25, flee=-3),
}

# --- Balance dials ------------------------------------------------------------
# The pacing numbers that used to be buried in combat.py and character.py.
# DIFFICULTIES above multiplies on top of everything here.
#
#   PLAYER_HP_BASE     flat HP everyone gets before their class die and CON.
#                      Health used to start near 120, which made potions (2d4+2),
#                      Hit Dice, traps and enemy damage dice - all sized for a
#                      D&D-scale pool - meaningless early and hopeless late.
#   XP_GROWTH          xp_to_next multiplier per level. At the old 1.4 the
#                      levels dried up around 6 while the floors kept scaling.
#   PACK_HP_BUDGET     a trash pack's shared HP range on floor 1.
#   PACK_HP_PER_FLOOR  how much that shared budget grows per floor. This is
#                      what decides how long deep-floor fights drag on.
#   BOSS_HP_SCALE      boss HP grows by this fraction of its base per floor.
PLAYER_HP_BASE = 16
XP_GROWTH = 1.25
PACK_HP_BUDGET = (18, 28)
PACK_HP_PER_FLOOR = 4
BOSS_HP_SCALE = 0.05

# --- Which spells each class may learn ---------------------------------------
# This is what stops a Cleric casting Fireball. It is enforced everywhere:
# character creation, level-up, the spellbook, and cast_spell itself.
#
# Every key must exist in SPELL_CATALOG at the bottom of this file. Classes
# with an empty list (Fighter, Rogue...) simply never see a spellbook.
#
# Order matters slightly: signature spells tend to be picked first when the
# game rolls a loadout for you, so put the iconic ones near the front.
CLASS_SPELLS = {
    'Bard': ['light', 'mage_hand', 'minor_illusion', 'prestidigitation', 'true_strike',
             'vicious_mockery', 'message',
             'cure_wounds', 'sleep', 'faerie_fire', 'detect_magic', 'identify',
             'thunderwave', 'healing_word', 'bane', 'charm_person', 'heroism',
             'hold_person', 'invisibility', 'blur', 'levitate', 'shatter',
             'mirror_image', 'gust_of_wind', 'silence', 'enhance_ability',
             'haste', 'fly', 'counterspell', 'hypnotic_pattern', 'fear',
             'dimension_door', 'greater_invisibility', 'polymorph', 'confusion',
             'banishment', 'hold_monster', 'mass_cure_wounds', 'dominate_person'],
    'Cleric': ['sacred_flame', 'light', 'true_strike', 'guidance', 'toll_the_dead',
               'cure_wounds', 'shield_bolt', 'detect_magic', 'identify', 'bless',
               'healing_word', 'bane', 'shield_of_faith',
               'spiritual_weapon', 'hold_person', 'levitate', 'invisibility', 'silence',
               'lesser_restoration', 'aid',
               'stinking_cloud', 'fly', 'spirit_guardians', 'revivify', 'beacon_of_hope',
               'death_ward', 'guardian_of_faith', 'banishment',
               'flame_strike', 'mass_cure_wounds', 'destructive_wave'],
    'Druid': ['thorn_whip', 'light', 'true_strike', 'guidance', 'produce_flame',
              'cure_wounds', 'faerie_fire', 'thunderwave', 'detect_magic', 'entangle',
              'healing_word', 'goodberry',
              'gust_of_wind', 'levitate', 'blur', 'moonbeam', 'barkskin',
              'lightning_bolt', 'stinking_cloud', 'fly', 'call_lightning', 'sleet_storm',
              'ice_storm', 'blight', 'polymorph', 'wall_of_fire', 'guardian_of_flame',
              'cone_of_cold', 'insect_plague', 'mass_cure_wounds'],
    'Paladin': ['cure_wounds', 'shield_bolt', 'detect_magic', 'bless', 'heroism',
                'shield_of_faith', 'searing_smite',
                'hold_person', 'levitate', 'aid', 'lesser_restoration',
                'haste', 'counterspell', 'revivify', 'beacon_of_hope',
                'death_ward', 'banishment', 'destructive_wave'],
    'Ranger': ['cure_wounds', 'detect_magic', 'faerie_fire', 'entangle', 'goodberry',
               'invisibility', 'gust_of_wind', 'levitate', 'barkskin', 'silence',
               'lightning_bolt', 'fly', 'stinking_cloud', 'sleet_storm', 'conjure_barrage',
               'ice_storm', 'greater_invisibility',
               'swift_quiver', 'insect_plague'],
    'Sorcerer': ['ray_of_frost', 'acid_splash', 'light', 'minor_illusion', 'mage_hand',
                 'prestidigitation', 'true_strike', 'fire_bolt', 'shocking_grasp',
                 'chill_touch', 'poison_spray',
                 'magic_missile', 'mage_armor', 'burning_hands', 'shield_spell', 'sleep', 'thunderwave',
                 'detect_magic', 'chromatic_orb', 'witch_bolt', 'charm_person',
                 'scorching_ray', 'misty_step', 'invisibility', 'blur', 'mirror_image',
                 'levitate', 'gust_of_wind', 'hold_person', 'shatter', 'enhance_ability',
                 'fireball', 'lightning_bolt', 'counterspell', 'fly', 'haste',
                 'stinking_cloud', 'hypnotic_pattern', 'fear', 'sleet_storm',
                 'ice_storm', 'wall_of_fire', 'dimension_door', 'blight', 'polymorph',
                 'greater_invisibility', 'confusion',
                 'cone_of_cold', 'hold_monster', 'chain_lightning', 'dominate_person',
                 'wall_of_force'],
    'Warlock': ['eldritch_blast', 'minor_illusion', 'mage_hand', 'prestidigitation',
                'true_strike', 'chill_touch', 'poison_spray', 'toll_the_dead',
                'burning_hands', 'shield_bolt', 'detect_magic', 'hex_spell',
                'witch_bolt', 'charm_person', 'armor_of_agathys',
                'hold_person', 'invisibility', 'misty_step', 'mirror_image', 'shatter',
                'counterspell', 'fly', 'stinking_cloud', 'fear', 'hypnotic_pattern',
                'dimension_door', 'blight', 'banishment', 'greater_invisibility',
                'hold_monster', 'dominate_person', 'soul_harvest'],
    'Wizard': ['ray_of_frost', 'acid_splash', 'light', 'minor_illusion', 'mage_hand',
               'prestidigitation', 'true_strike', 'fire_bolt', 'shocking_grasp',
               'chill_touch', 'poison_spray', 'toll_the_dead', 'message',
               'magic_missile', 'mage_armor', 'burning_hands', 'shield_spell', 'sleep', 'detect_magic',
               'identify', 'thunderwave', 'shield_bolt', 'chromatic_orb', 'witch_bolt',
               'charm_person', 'bane',
               'scorching_ray', 'misty_step', 'invisibility', 'blur', 'levitate',
               'gust_of_wind', 'mirror_image', 'hold_person', 'shatter', 'silence',
               'enhance_ability',
               'fireball', 'lightning_bolt', 'counterspell', 'fly', 'haste',
               'stinking_cloud', 'hypnotic_pattern', 'fear', 'sleet_storm',
               'ice_storm', 'wall_of_fire', 'dimension_door', 'blight', 'polymorph',
               'greater_invisibility', 'confusion', 'arcane_eye', 'guardian_of_flame',
               'cone_of_cold', 'hold_monster', 'chain_lightning', 'wall_of_force',
               'dominate_person', 'telekinesis'],
    # martial classes have no spell list at all
    'Barbarian': [], 'Fighter': [], 'Monk': [], 'Rogue': [],
}

# --- Spells usable with no enemies around ------------------------------------
# Healing and utility. Anything NOT listed here is refused outside combat,
# before any spell slot is spent, so you never waste a slot on nothing.
#
# Add a spell here if it should be castable while exploring.
OUT_OF_COMBAT_SPELLS = {
    'light', 'mage_hand', 'minor_illusion', 'prestidigitation', 'guidance',
    'message', 'produce_flame',
    'detect_magic', 'identify', 'cure_wounds', 'healing_word', 'goodberry',
    'levitate', 'fly', 'invisibility', 'misty_step', 'greater_invisibility', 'mage_armor',
    'enhance_ability', 'lesser_restoration', 'aid', 'barkskin', 'shield_of_faith',
    'heroism', 'death_ward', 'arcane_eye', 'dimension_door', 'mass_cure_wounds',
    'beacon_of_hope', 'revivify', 'swift_quiver',
}

# --- Where rolled ability scores go ------------------------------------------
# Best rolled score goes to the first ability listed, second-best to the next,
# and so on. Used by Quick Start to build a sensible character automatically
# (the character creator lets you assign them by hand instead).
#
# The first entry should be the ability that class actually fights or casts
# with - it is the one that gets the 18.
CLASS_STAT_PRIORITY = {
    'Barbarian': ['strength', 'constitution', 'dexterity', 'wisdom', 'charisma', 'intelligence'],
    'Bard':      ['charisma', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'strength'],
    'Cleric':    ['wisdom', 'constitution', 'strength', 'charisma', 'dexterity', 'intelligence'],
    'Druid':     ['wisdom', 'constitution', 'dexterity', 'intelligence', 'charisma', 'strength'],
    'Fighter':   ['strength', 'constitution', 'dexterity', 'wisdom', 'charisma', 'intelligence'],
    'Monk':      ['dexterity', 'wisdom', 'constitution', 'strength', 'charisma', 'intelligence'],
    'Paladin':   ['strength', 'charisma', 'constitution', 'wisdom', 'dexterity', 'intelligence'],
    'Ranger':    ['dexterity', 'wisdom', 'constitution', 'strength', 'intelligence', 'charisma'],
    'Rogue':     ['dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma', 'strength'],
    'Sorcerer':  ['charisma', 'constitution', 'dexterity', 'wisdom', 'intelligence', 'strength'],
    'Warlock':   ['charisma', 'constitution', 'dexterity', 'wisdom', 'intelligence', 'strength'],
    'Wizard':    ['intelligence', 'constitution', 'dexterity', 'wisdom', 'charisma', 'strength'],
}

# --- Subclasses ---------------------------------------------------------------
# Every class has two paths, chosen at character creation (D&D-style archetypes:
# domains, colleges, oaths, circles, bloodlines...). They are PURE DATA: the
# effect keys are the very same ones magic items use (see the table above
# MAGIC_ITEMS), because subclass effects are folded into gear_effects() and so
# reach AC, attack, damage, crits, damage reduction, regeneration, checks and
# fleeing with no extra code. One extra key exists just for subclasses:
#
#   max_hp_per_level   bonus maximum HP for every character level you have
#
# Adding a subclass = adding a dict entry here. Nothing else.
SUBCLASSES = {
    'Barbarian': {
        'Path of the Berserker': dict(
            desc='You fight in a red-eyed frenzy. +2 to every damage roll.',
            dmg=2),
        'Path of the Bear Totem': dict(
            desc='The bear spirit shrugs off blows. 1 damage reduction and +1 max HP per level.',
            dr=1, max_hp_per_level=1),
    },
    'Bard': {
        'College of Lore': dict(
            desc='You know a cutting word for everything. +3 to skill checks and +1 spell attack.',
            check_bonus=3, spell_atk=1),
        'College of Valor': dict(
            desc='Your songs are for the battle line. +1 AC and +1 to attack rolls.',
            ac=1, atk=1),
    },
    'Cleric': {
        'Life Domain': dict(
            desc='Your god mends what breaks. Regain 1 HP each combat round and +1 max HP per level.',
            regen=1, max_hp_per_level=1),
        'War Domain': dict(
            desc='Your god marches with you. +1 to attack rolls and +1 damage.',
            atk=1, dmg=1),
    },
    'Druid': {
        'Circle of the Moon': dict(
            desc='The beast within lends fang and hide. +1 damage and +1 max HP per level.',
            dmg=1, max_hp_per_level=1),
        'Circle of the Land': dict(
            desc='The land itself sustains you. Regain 1 HP each combat round and +2 to skill checks.',
            regen=1, check_bonus=2),
    },
    'Fighter': {
        'Champion': dict(
            desc='Raw physical perfection. Critical hits on 19 or 20, and +1 to skill checks.',
            crit_range=19, check_bonus=1),
        'Battle Master': dict(
            desc='Fighting is a science and you have studied. +1 to attack rolls and +2 to skill checks.',
            atk=1, check_bonus=2),
    },
    'Monk': {
        'Way of the Open Hand': dict(
            desc='Nothing touches you that you do not allow. +1 to attack rolls and +2 when fleeing.',
            atk=1, flee_bonus=2),
        'Way of Shadow': dict(
            desc='You strike from darkness. +1 damage and +3 to skill checks.',
            dmg=1, check_bonus=3),
    },
    'Paladin': {
        'Oath of Devotion': dict(
            desc='A shining example: your presence steadies your arm. +1 AC and +1 to attack rolls.',
            ac=1, atk=1),
        'Oath of Vengeance': dict(
            desc='Someone must answer for what was done. +2 to every damage roll.',
            dmg=2),
    },
    'Ranger': {
        'Hunter': dict(
            desc='You know exactly where to put the arrow. +2 to every damage roll.',
            dmg=2),
        'Beast Master': dict(
            desc='Your companion watches over you. Regain 1 HP each combat round and +2 to skill checks.',
            regen=1, check_bonus=2),
    },
    'Rogue': {
        'Thief': dict(
            desc='Locks, ledges and pockets are all yours. +3 to skill checks and +2 when fleeing.',
            check_bonus=3, flee_bonus=2),
        'Assassin': dict(
            desc='The first cut is the one that matters. Critical hits on 19 or 20, and +1 damage.',
            crit_range=19, dmg=1),
    },
    'Sorcerer': {
        'Draconic Bloodline': dict(
            desc='Dragon blood thickens your hide. +1 AC and +1 max HP per level.',
            ac=1, max_hp_per_level=1),
        'Wild Magic': dict(
            desc='Chaos crackles around you and, mostly, helps. +1 spell attack and +2 when fleeing.',
            spell_atk=1, flee_bonus=2),
    },
    'Warlock': {
        'The Fiend': dict(
            desc="Your patron keeps its investments alive. +1 spell attack and +1 max HP per level.",
            spell_atk=1, max_hp_per_level=1),
        'The Hexblade': dict(
            desc='Your pact lives in your weapon. +1 to attack rolls and +1 damage.',
            atk=1, dmg=1),
    },
    'Wizard': {
        'School of Evocation': dict(
            desc='You sculpt raw destruction. +1 spell attack and +1 damage.',
            spell_atk=1, dmg=1),
        'School of Abjuration': dict(
            desc='An arcane ward hums around you. +1 AC and 1 damage reduction.',
            ac=1, dr=1),
    },
}

# --- Everything a new character carries --------------------------------------
# Granted to every class, on top of that class's own extra_items in CLASSES.
# Repeat a name to start with more than one (two potions here).
STARTING_KIT = ['potion', 'potion', 'torch', 'rope', 'map', 'ration']

# --- Ability Score Improvements ----------------------------------------------
# Reaching one of these levels lets you raise your ability scores: either +2 to
# one ability or +1 to two of them. Scores are capped at ABILITY_CAP.
ASI_LEVELS = (4, 8, 12, 16, 19)
ABILITY_CAP = 20

# The highest level a character can grow to, and the highest they may be
# created at. Starting at 9 or 10 is how you get to try level 4 and 5 spells
# without grinding for them first.
MAX_CHARACTER_LEVEL = 20
MAX_START_LEVEL = 10

# --- Item descriptions -------------------------------------------------------
# name: (category, what_it_does)
#
# Shown under the inventory list when an item is selected. Weapons, armour and
# shields are NOT listed here - their descriptions are generated from the
# tables above by describe_item() in items.py, so their stats can never go out
# of date. Magic items describe themselves from MAGIC_ITEMS.
#
# This is description text only. The actual effect of using an item is coded
# in apply_item_effect() in items.py.
ITEM_INFO = {
    # --- healing ---
    'potion':         ('Consumable', 'Restores 2d4 + 2 HP. In a fight it costs your bonus action.'),
    'greater potion': ('Consumable', 'Restores 4d4 + 4 HP.'),
    'superior potion': ('Consumable', 'Restores 8d4 + 8 HP - most of a full bar.'),
    'elixir of life': ('Consumable', 'Restores you to full health, whatever state you are in.'),
    'healing herbs':  ('Consumable', 'Restores 1d6 + 2 HP. Cheap, plentiful, and slightly bitter.'),
    'bandages':       ('Consumable', 'Out of combat only: restores 1d8 + 3 HP while you patch yourself up.'),
    'ration':         ('Consumable', 'Out of combat only: a hot meal restores 1d6 HP and settles the nerves.'),
    'elixir of fortitude': ('Consumable', 'Grants 12 temporary HP that soak damage before your own.'),
    'antidote':       ('Consumable', 'Ends poison and clears the lingering effects of a bad trap.'),
    'bezoar':         ('Consumable', 'A stone from a beast\'s gut. Ends poison and restores 1d8 HP.'),

    # --- thrown and offensive ---
    'oil flask':      ('Thrown', 'Shatters on your target for 1d10 fire damage. Never misses cleanly.'),
    'alchemists fire': ('Thrown', 'Clinging fire: 2d6 damage to your target and it keeps burning next round.'),
    'acid vial':      ('Thrown', '2d6 acid damage and the target\'s armour is eaten away (-2 AC).'),
    'firebomb':       ('Thrown', '3d6 fire damage to every enemy in the room.'),
    'holy water':     ('Thrown', '2d6 radiant damage - devastating against undead and fiends.'),
    'thunderstone':   ('Thrown', '2d8 thunder damage to all enemies and they reel (-2 to their attacks).'),
    'net':            ('Thrown', 'Tangles one enemy so it misses its next turn.'),
    'caltrops':       ('Thrown', 'Scattered across the floor: every enemy takes 1d4 and struggles to close.'),
    'smoke bomb':     ('Thrown', 'Blinding smoke: enemies attack at -4 this round and fleeing becomes easy.'),

    # --- combat prep ---
    'whetstone':      ('Prep', 'Hones your blade: +2 weapon damage for the rest of this fight.'),
    'poison vial':    ('Prep', 'Coats your weapon: +1d6 poison damage on every hit for this fight.'),
    'blessed oil':    ('Prep', 'Anoints your weapon: +1d6 radiant damage on every hit for this fight.'),
    'lucky coin':     ('Prep', 'Flip it before a roll: your next attack or check gets +4.'),

    # --- light and tools ---
    'torch':   ('Consumable', 'Light it in combat for +1 on your next attack roll; outside combat it lights the room.'),
    'lantern': ('Consumable', 'Light it in combat to dazzle a foe for +1 on your next attack roll.'),
    'map':     ('Consumable', 'Reveals the entire layout of the dungeon floor you are on.'),
    'spyglass': ('Tool (reusable)', 'Reveals every room adjacent to the ones you have already walked.'),
    'rope':    ('Tool (reusable)', 'Kept when used. Lets you spring dungeon traps from a safe distance.'),
    'grappling hook': ('Tool (reusable)', 'Kept when used. Hauls you past a trap or up out of a pit.'),
    'thieves tools': ('Tool (reusable)', 'Kept when used. +3 on every lock and trap check while it is in your bag.'),
    'crowbar':  ('Tool (reusable)', 'Kept when used. +3 on every Strength check to force something open.'),
    'climbing gear': ('Tool (reusable)', 'Kept when used. +3 on Endurance checks to vault, climb or leap.'),
    'shovel':   ('Tool (reusable)', 'Kept when used. Sometimes turns up something buried in an empty room.'),

    # --- scrolls ---
    'scroll of magic missile': ('Scroll', 'Casts Magic Missile once, with no slot and no class restriction.'),
    'scroll of cure wounds':   ('Scroll', 'Casts Cure Wounds once, with no slot and no class restriction.'),
    'scroll of fireball':      ('Scroll', 'Casts Fireball once, with no slot and no class restriction.'),
    'scroll of lightning bolt': ('Scroll', 'Casts Lightning Bolt once, with no slot and no class restriction.'),
    'scroll of haste':         ('Scroll', 'Casts Haste once, with no slot and no class restriction.'),
    'scroll of ice storm':     ('Scroll', 'Casts Ice Storm once, with no slot and no class restriction.'),
    'scroll of cone of cold':  ('Scroll', 'Casts Cone of Cold once, with no slot and no class restriction.'),
    'scroll of revivify':      ('Scroll', 'Casts Revivify once - a hard shield against the next killing blow.'),

    # --- valuables ---
    'ruby':        ('Valuable', 'Worth a great deal to the right merchant. Sell it at a shop.'),
    'sapphire':    ('Valuable', 'Worth a great deal to the right merchant. Sell it at a shop.'),
    'ancient coin': ('Valuable', 'Older than the dungeon. Collectors pay well. Sell it at a shop.'),
    'silver idol': ('Valuable', 'A grotesque little statue in solid silver. Sell it at a shop.'),
    'gold ingot':  ('Valuable', 'Heavy, plain, and unmistakably valuable. Sell it at a shop.'),
}

# --- Prices for non-gear items -----------------------------------------------
# What the shop charges. Selling something back pays SELL_RATE of this.
# Weapons, armour, shields and magic items take their price from their own
# tables instead.
ITEM_PRICES = {
    'potion': 7, 'greater potion': 22, 'superior potion': 60, 'elixir of life': 150,
    'healing herbs': 5, 'bandages': 6, 'ration': 3, 'elixir of fortitude': 30,
    'antidote': 14, 'bezoar': 25,
    'oil flask': 6, 'alchemists fire': 20, 'acid vial': 18, 'firebomb': 45,
    'holy water': 24, 'thunderstone': 35, 'net': 10, 'caltrops': 12, 'smoke bomb': 26,
    'whetstone': 12, 'poison vial': 30, 'blessed oil': 30, 'lucky coin': 20,
    'torch': 5, 'lantern': 9, 'map': 12, 'spyglass': 55,
    'rope': 7, 'grappling hook': 18, 'thieves tools': 40, 'crowbar': 16,
    'climbing gear': 22, 'shovel': 10,
    'scroll of magic missile': 45, 'scroll of cure wounds': 45,
    'scroll of fireball': 130, 'scroll of lightning bolt': 130,
    'scroll of haste': 140, 'scroll of ice storm': 190,
    'scroll of cone of cold': 240, 'scroll of revivify': 200,
    'ruby': 120, 'sapphire': 140, 'ancient coin': 80, 'silver idol': 200,
    'gold ingot': 260,
}

# Fraction of an item's price you get back when you sell it to a merchant.
SELL_RATE = 0.5

# Loot that exists purely to be sold. Picking one up is always good news.
VALUABLES = {'ruby', 'sapphire', 'ancient coin', 'silver idol', 'gold ingot'}

# --- Scrolls -----------------------------------------------------------------
# scroll item name -> the spell key it casts, and the slot level it casts at.
# Using a scroll ignores your class list and costs no spell slot.
SCROLLS = {
    'scroll of magic missile':  ('magic_missile', 1),
    'scroll of cure wounds':    ('cure_wounds', 1),
    'scroll of fireball':       ('fireball', 3),
    'scroll of lightning bolt': ('lightning_bolt', 3),
    'scroll of haste':          ('haste', 3),
    'scroll of ice storm':      ('ice_storm', 4),
    'scroll of cone of cold':   ('cone_of_cold', 5),
    'scroll of revivify':       ('revivify', 3),
}

# --- The random drop pool ----------------------------------------------------
# What a defeated enemy or a small hoard might leave behind. Repeat a name to
# make it more likely; the common supplies appear several times each.
COMMON_LOOT = [
    'potion', 'potion', 'potion', 'torch', 'torch', 'rope', 'map', 'lantern',
    'ration', 'ration', 'healing herbs', 'healing herbs', 'bandages',
    'greater potion', 'oil flask', 'oil flask', 'whetstone', 'net',
    'alchemists fire', 'acid vial', 'holy water', 'caltrops', 'smoke bomb',
    'antidote', 'lucky coin', 'poison vial', 'crowbar', 'shovel',
    'thunderstone', 'elixir of fortitude', 'grappling hook', 'climbing gear',
    'scroll of magic missile', 'scroll of cure wounds',
]

# Rarer things that turn up in chests and on deeper floors.
DEEP_LOOT = [
    'greater potion', 'superior potion', 'firebomb', 'thieves tools', 'spyglass',
    'blessed oil', 'bezoar', 'scroll of fireball', 'scroll of lightning bolt',
    'scroll of haste', 'ruby', 'sapphire', 'ancient coin', 'silver idol',
    'scroll of ice storm', 'scroll of revivify', 'elixir of life', 'gold ingot',
    'scroll of cone of cold',
]

# --- Spells ------------------------------------------------------------------
# key: (display_name, description, spell_level, action_cost)
#
#   key            internal name, used in CLASS_SPELLS and in cast_spell()
#   display_name   shown in the spellbook
#   description    shown in the spellbook - keep it short
#   spell_level    0 = cantrip (free, unlimited). 1-5 spend a slot of that level.
#   action_cost    'action' or 'bonus' - which part of your turn it uses
#
# Adding an entry here makes a spell EXIST but do nothing interesting. To make
# it work you also need to:
#   1. list it under the right classes in CLASS_SPELLS above
#   2. add its effect as a branch in cast_spell() in spells.py
#   3. add it to OUT_OF_COMBAT_SPELLS if it should work while exploring
#   4. add an SPELL_UPCAST line if a bigger slot should do more
#
# CANTRIPS SCALE WITH YOU, not with slots: their damage dice go up at
# character levels 5, 11 and 17 (see cantrip_dice in character.py).
SPELL_CATALOG = {
    # --- Cantrips (level 0, free and unlimited) ---
    'ray_of_frost':     ('Ray of Frost', 'Cantrip - 1d8 cold, and the target is slowed', 0, 'action'),
    'fire_bolt':        ('Fire Bolt', 'Cantrip - 1d10 fire at range', 0, 'action'),
    'shocking_grasp':   ('Shocking Grasp', 'Cantrip - 1d8 lightning; the target loses its reaction', 0, 'action'),
    'chill_touch':      ('Chill Touch', 'Cantrip - 1d8 necrotic; the target cannot heal', 0, 'action'),
    'poison_spray':     ('Poison Spray', 'Cantrip - 1d12 poison on a failed save', 0, 'action'),
    'toll_the_dead':    ('Toll the Dead', 'Cantrip - 1d8 necrotic, 1d12 if already wounded', 0, 'action'),
    'acid_splash':      ('Acid Splash', 'Cantrip - 1d6 acid to two nearby foes', 0, 'action'),
    'sacred_flame':     ('Sacred Flame', 'Cantrip - 1d8 radiant, no cover allowed', 0, 'action'),
    'eldritch_blast':   ('Eldritch Blast', 'Cantrip - 1d10 force, extra beams as you level', 0, 'action'),
    'thorn_whip':       ('Thorn Whip', 'Cantrip - 1d6 piercing and a hard yank', 0, 'action'),
    'vicious_mockery':  ('Vicious Mockery', 'Cantrip - 1d4 psychic and the target attacks at -2', 0, 'action'),
    'produce_flame':    ('Produce Flame', 'Cantrip - 1d8 fire, and it lights the room', 0, 'action'),
    'light':            ('Light', 'Cantrip - illuminate an area and the rooms beside it', 0, 'action'),
    'guidance':         ('Guidance', 'Cantrip - +1d4 on your next ability check', 0, 'bonus'),
    'message':          ('Message', 'Cantrip - a whisper carries: reveals nearby rooms', 0, 'bonus'),
    'minor_illusion':   ('Minor Illusion', 'Cantrip - lure one enemy away from the next pack', 0, 'action'),
    'prestidigitation': ('Prestidigitation', 'Cantrip - small magical tricks and small comforts', 0, 'action'),
    'mage_hand':        ('Mage Hand', 'Cantrip - a spectral hand springs the next trap', 0, 'action'),
    'true_strike':      ('True Strike', 'Cantrip - +2 on your next attack roll', 0, 'bonus'),

    # --- Level 1 ---
    'magic_missile':    ('Magic Missile', 'L1 - 3 darts of 1d4+1, never misses', 1, 'action'),
    'mage_armor':       ('Mage Armor', 'L1 - a film of force: AC 13 + DEX while unarmored, until your next long rest', 1, 'action'),
    'burning_hands':    ('Burning Hands', 'L1 - 3d6 fire in a cone', 1, 'action'),
    'chromatic_orb':    ('Chromatic Orb', 'L1 - 3d8 of an element you choose', 1, 'action'),
    'witch_bolt':       ('Witch Bolt', 'L1 - 2d12 lightning and an arcing tether', 1, 'action'),
    'thunderwave':      ('Thunderwave', 'L1 - 2d8 thunder to all, and they are pushed back', 1, 'action'),
    'shield_bolt':      ('Shield Bolt', 'L1 - 1d8 force and a small knockback', 1, 'action'),
    'cure_wounds':      ('Cure Wounds', 'L1 - heal 1d8 + casting modifier', 1, 'action'),
    'healing_word':     ('Healing Word', 'L1 - heal 1d4 + modifier as a bonus action', 1, 'bonus'),
    'goodberry':        ('Goodberry', 'L1 - conjure berries: adds healing herbs to your bag', 1, 'action'),
    'shield_spell':     ('Shield', 'L1 - +5 AC until the end of the round', 1, 'bonus'),
    'armor_of_agathys': ('Armor of Agathys', 'L1 - 10 temp HP, and attackers take cold damage', 1, 'action'),
    'shield_of_faith':  ('Shield of Faith', 'L1 - +2 AC for the rest of the fight', 1, 'bonus'),
    'bless':            ('Bless', 'L1 - +2 to your attack rolls for the fight', 1, 'action'),
    'bane':             ('Bane', 'L1 - enemies attack at -3 for the fight', 1, 'action'),
    'heroism':          ('Heroism', 'L1 - 8 temporary HP and immunity to fear', 1, 'action'),
    'sleep':            ('Sleep', 'L1 - drops the weakest foes outright', 1, 'action'),
    'charm_person':     ('Charm Person', 'L1 - one foe stands down and stops attacking', 1, 'action'),
    'entangle':         ('Entangle', 'L1 - roots every enemy that fails its save', 1, 'action'),
    'faerie_fire':      ('Faerie Fire', 'L1 - outlines enemies; their AC drops by 2', 1, 'action'),
    'searing_smite':    ('Searing Smite', 'L1 - your next hit deals +2d6 fire', 1, 'bonus'),
    'hex_spell':        ('Hex', 'L1 - +1d6 damage on all your hits this fight', 1, 'bonus'),
    'detect_magic':     ('Detect Magic', 'L1 - reveals hidden caches on this floor', 1, 'action'),
    'identify':         ('Identify', 'L1 - reveals every trap on this floor', 1, 'action'),

    # --- Level 2 ---
    'scorching_ray':    ('Scorching Ray', 'L2 - 3 rays of 2d6 fire, aimed as you like', 2, 'action'),
    'shatter':          ('Shatter', 'L2 - 3d8 thunder to everything nearby', 2, 'action'),
    'moonbeam':         ('Moonbeam', 'L2 - 2d10 radiant, and the beam lingers', 2, 'action'),
    'spiritual_weapon': ('Spiritual Weapon', 'L2 - a floating blade strikes for 1d8 each round', 2, 'bonus'),
    'hold_person':      ('Hold Person', 'L2 - paralyses a humanoid foe', 2, 'action'),
    'silence':          ('Silence', 'L2 - enemy casters and shouts are smothered (-2 to attacks)', 2, 'action'),
    'misty_step':       ('Misty Step', 'L2 - a short teleport; makes escape far easier', 2, 'bonus'),
    'invisibility':     ('Invisibility', 'L2 - enemies attack you at -4', 2, 'action'),
    'blur':             ('Blur', 'L2 - your outline wavers; enemies attack at -2', 2, 'bonus'),
    'mirror_image':     ('Mirror Image', 'L2 - duplicates flicker around you; enemies at -3', 2, 'bonus'),
    'levitate':         ('Levitate', 'L2 - float over the next wall that blocks you', 2, 'action'),
    'gust_of_wind':     ('Gust of Wind', 'L2 - staggers your foes; -2 to their attacks', 2, 'action'),
    'barkskin':         ('Barkskin', 'L2 - your hide toughens: 3 damage reduction this fight', 2, 'bonus'),
    'enhance_ability':  ('Enhance Ability', 'L2 - +4 on your ability checks for a while', 2, 'action'),
    'lesser_restoration': ('Lesser Restoration', 'L2 - ends poison and lingering afflictions', 2, 'action'),
    'aid':              ('Aid', 'L2 - +10 maximum and current HP for this delve', 2, 'action'),

    # --- Level 3 ---
    'fireball':         ('Fireball', 'L3 - 8d6 fire to everything in the room', 3, 'action'),
    'lightning_bolt':   ('Lightning Bolt', 'L3 - 8d6 lightning in a line', 3, 'action'),
    'call_lightning':   ('Call Lightning', 'L3 - 3d10 to all, and the storm keeps rolling', 3, 'action'),
    'spirit_guardians': ('Spirit Guardians', 'L3 - 3d8 to all foes and they close at -2', 3, 'action'),
    'sleet_storm':      ('Sleet Storm', 'L3 - the floor ices over; enemies fall and lose a turn', 3, 'action'),
    'stinking_cloud':   ('Stinking Cloud', 'L3 - retching foes lose their next turn', 3, 'action'),
    'hypnotic_pattern': ('Hypnotic Pattern', 'L3 - dazzling colours hold several foes still', 3, 'action'),
    'fear':             ('Fear', 'L3 - the weakest foes break and flee outright', 3, 'action'),
    'haste':            ('Haste', 'L3 - +2 AC and an extra action each round', 3, 'action'),
    'fly':              ('Fly', 'L3 - carries you over the next wall that blocks you', 3, 'action'),
    'counterspell':     ('Counterspell', 'L3 - shuts down an enemy caster mid-cast', 3, 'bonus'),
    'beacon_of_hope':   ('Beacon of Hope', 'L3 - healing is doubled for the rest of the fight', 3, 'action'),
    'revivify':         ('Revivify', 'L3 - a ward that catches you at 1 HP instead of death', 3, 'action'),
    'guardian_of_faith': ('Guardian of Faith', 'L3 - a spectral warden strikes for 2d8 each round', 3, 'action'),
    'conjure_barrage':  ('Conjure Barrage', 'L3 - a volley of spectral arrows: 4d8 to all', 3, 'action'),

    # --- Level 4 ---
    'ice_storm':        ('Ice Storm', 'L4 - 4d6 bludgeoning + 4d6 cold to everything', 4, 'action'),
    'wall_of_fire':     ('Wall of Fire', 'L4 - a burning wall: 5d8 now and it keeps burning', 4, 'action'),
    'blight':           ('Blight', 'L4 - 8d8 necrotic to one foe; withers plants outright', 4, 'action'),
    'polymorph':        ('Polymorph', 'L4 - turns a foe into something entirely harmless', 4, 'action'),
    'confusion':        ('Confusion', 'L4 - foes stagger and attack each other', 4, 'action'),
    'greater_invisibility': ('Greater Invisibility', 'L4 - -6 to enemy attacks for the fight', 4, 'action'),
    'banishment':       ('Banishment', 'L4 - hurls a foe out of the room entirely', 4, 'action'),
    'dimension_door':   ('Dimension Door', 'L4 - step through space; escape is guaranteed', 4, 'bonus'),
    'death_ward':       ('Death Ward', 'L4 - the next killing blow leaves you at 1 HP', 4, 'action'),
    'arcane_eye':       ('Arcane Eye', 'L4 - reveals the whole floor, traps and all', 4, 'action'),
    'guardian_of_flame': ('Guardian of Flame', 'L4 - a fire elemental fights beside you', 4, 'action'),

    # --- Level 5 ---
    'cone_of_cold':     ('Cone of Cold', 'L5 - 8d8 cold in a wide, killing arc', 5, 'action'),
    'flame_strike':     ('Flame Strike', 'L5 - 4d6 fire + 4d6 radiant from above', 5, 'action'),
    'chain_lightning':  ('Chain Lightning', 'L5 - 10d8 that leaps from foe to foe', 5, 'action'),
    'destructive_wave': ('Destructive Wave', 'L5 - 5d6 thunder + 5d6 radiant, and foes are floored', 5, 'action'),
    'hold_monster':     ('Hold Monster', 'L5 - paralyses anything, bosses included', 5, 'action'),
    'dominate_person':  ('Dominate Person', 'L5 - a foe turns and fights for you', 5, 'action'),
    'insect_plague':    ('Insect Plague', 'L5 - a biting swarm: 5d10 and it lingers', 5, 'action'),
    'mass_cure_wounds': ('Mass Cure Wounds', 'L5 - heal 5d8 + modifier', 5, 'action'),
    'wall_of_force':    ('Wall of Force', 'L5 - an unbreakable wall: nothing can reach you this round', 5, 'action'),
    'telekinesis':      ('Telekinesis', 'L5 - hurls a foe into the wall for 6d8 and stuns it', 5, 'action'),
    'swift_quiver':     ('Swift Quiver', 'L5 - your quiver never empties: two extra attacks each round', 5, 'bonus'),
    'soul_harvest':     ('Soul Harvest', 'L5 - 6d10 necrotic, and you heal for half of it', 5, 'action'),
}

# --- What a bigger slot buys you ---------------------------------------------
# key -> the one-line note shown in the spellbook next to the upcast buttons.
# The actual scaling is implemented in cast_spell() in spells.py; this is the
# text that tells the player about it. A spell with no entry here does not
# improve when cast from a higher slot (but casting it that way still works).
SPELL_UPCAST = {
    'magic_missile':  '+1 dart per extra slot level',
    'burning_hands':  '+1d6 per extra slot level',
    'chromatic_orb':  '+1d8 per extra slot level',
    'witch_bolt':     '+1d12 per extra slot level',
    'thunderwave':    '+1d8 per extra slot level',
    'shield_bolt':    '+1d8 per extra slot level',
    'cure_wounds':    '+1d8 healing per extra slot level',
    'healing_word':   '+1d4 healing per extra slot level',
    'goodberry':      '+2 more berries per extra slot level',
    'armor_of_agathys': '+5 temp HP per extra slot level',
    'heroism':        '+4 temp HP per extra slot level',
    'sleep':          'drops much tougher foes',
    'entangle':       'harder to shake off',
    'searing_smite':  '+1d6 smite damage per extra slot level',
    'hex_spell':      '+1d6 hex damage every two extra levels',
    'scorching_ray':  '+1 ray per extra slot level',
    'shatter':        '+1d8 per extra slot level',
    'moonbeam':       '+1d10 per extra slot level',
    'spiritual_weapon': '+1d8 per two extra slot levels',
    'hold_person':    'harder to resist',
    'invisibility':   'lasts and hides you better',
    'aid':            '+5 more HP per extra slot level',
    'fireball':       '+1d6 per extra slot level',
    'lightning_bolt': '+1d6 per extra slot level',
    'call_lightning': '+1d10 per extra slot level',
    'spirit_guardians': '+1d8 per extra slot level',
    'conjure_barrage': '+1d8 per extra slot level',
    'stinking_cloud': 'harder to resist',
    'hypnotic_pattern': 'catches more foes',
    'fear':           'routs tougher foes',
    'haste':          '+1 round of Haste per extra slot level',
    'guardian_of_faith': '+1d8 per extra slot level',
    'ice_storm':      '+1d6 cold per extra slot level',
    'wall_of_fire':   '+1d8 per extra slot level',
    'blight':         '+1d8 per extra slot level',
    'confusion':      'catches more foes',
    'banishment':     'can banish tougher things',
    'cone_of_cold':   '+1d8 per extra slot level',
    'flame_strike':   '+1d6 of each type per extra slot level',
    'chain_lightning': '+1d8 per extra slot level',
    'destructive_wave': '+1d6 of each type per extra slot level',
    'insect_plague':  '+1d10 per extra slot level',
    'mass_cure_wounds': '+1d8 healing per extra slot level',
    'telekinesis':    '+1d8 per extra slot level',
    'soul_harvest':   '+1d10 per extra slot level',
}

# The spell slot levels the game tracks. Everything that loops over slots uses
# this, so widening the game to level 6 spells is a one-line change here plus
# entries in compute_slots (character.py).
SPELL_LEVELS = (1, 2, 3, 4, 5)

# --- Bosses ------------------------------------------------------------------
# One boss guards the stairs on every BOSS_EVERY floors. They are ordinary
# enemies with a few extra keys, so everything that already works on an enemy
# (targeting, damage, holds) works on them too.
#
#   title       the line printed when they appear
#   hp          base health before floor and difficulty scaling
#   ac          armour class
#   atk         attack bonus
#   dmg         damage die of a single attack
#   attacks     how many times it swings per round
#   special     the key of its signature move (see boss_special in combat.py)
#   minions     how many lesser foes fight alongside it
#   resist      damage types it takes half from
#   vulnerable  damage types it takes extra from
#   loot        magic item rarity it is guaranteed to drop
#
# A boss also enrages below half health: +2 to hit and one extra attack.
BOSSES = {
    'goblin warlord': dict(
        tier=0, hp=34, ac=14, atk=3, dmg=6, attacks=2, special='rally',
        minions=1, resist=[], vulnerable=['radiant'], loot='Uncommon',
        title='A goblin in stolen plate hauls itself onto a heap of shields and bellows.'),
    'the gravebound': dict(
        tier=0, hp=40, ac=15, atk=3, dmg=6, attacks=2, special='drain',
        minions=1, resist=['necrotic', 'poison'], vulnerable=['radiant'], loot='Uncommon',
        title='Bones knit themselves together out of the floor, wearing a crown of teeth.'),
    'brood mother': dict(
        tier=1, hp=52, ac=15, atk=5, dmg=8, attacks=2, special='web',
        minions=2, resist=['poison'], vulnerable=['fire'], loot='Rare',
        title='The ceiling shifts. It is not a ceiling. Eight eyes open at once.'),
    'the flayed priest': dict(
        tier=1, hp=58, ac=16, atk=5, dmg=8, attacks=2, special='curse',
        minions=1, resist=['necrotic'], vulnerable=['radiant'], loot='Rare',
        title='A hooded figure lowers its censer and the room goes very quiet.'),
    'stone tyrant': dict(
        tier=2, hp=90, ac=17, atk=6, dmg=10, attacks=3, special='quake',
        minions=1, resist=['fire', 'lightning', 'poison'], vulnerable=['thunder'], loot='Very Rare',
        title='A slab of the far wall stands up, and keeps standing up.'),
    'wyrm of the deep vault': dict(
        tier=2, hp=108, ac=18, atk=7, dmg=12, attacks=3, special='breath',
        minions=0, resist=['fire', 'poison', 'necrotic'], vulnerable=['cold'], loot='Legendary',
        title='Something enormous uncoils in the dark, and the heat arrives before it does.'),
}

# A boss guards the stairs on every Nth floor.
BOSS_EVERY = 3

# --- Combat tactics: range, cover, morale ------------------------------------
# Enemies now stand somewhere: 'near' (in your face) or 'far' (hanging back).
# Melee weapons only reach near targets - but attacking a far one simply closes
# the distance first (your free move for the round), so nothing ever refuses.
# Ranged weapons and all spells work at any distance.

# These enemies attack from range and open the fight standing far back.
RANGED_ENEMIES = {'kobold', 'cultist', 'harpy', 'fire elemental', 'young wyrm'}

# Flavour for their ranged attacks in the log.
RANGED_VERBS = {
    'kobold': 'slings a sharp stone',
    'cultist': 'hurls a bolt of dark fire',
    'harpy': 'rakes you with a screeching dive',
    'fire elemental': 'flings a gout of flame',
    'young wyrm': 'spits a lance of fire',
}

# Mindless, bound or elemental things never lose their nerve (no morale checks).
FEARLESS_ENEMIES = {'skeleton', 'zombie', 'ghost', 'animated armor', 'wraith',
                    'stone golem', 'fire elemental'}

# Cover: some rooms contain something worth ducking behind. Take Cover (in the
# Move menu) grants +COVER_AC against ranged attacks and halves a boss's breath
# or quake. Ranged enemies use the same obstacle against you.
OBSTACLE_CHANCE = 0.6
COVER_AC = 2
OBSTACLES = [
    ('a toppled pillar', 'A toppled pillar lies across the room - solid cover.'),
    ('a heap of rubble', 'A heap of rubble rises waist-high near the wall.'),
    ('an old barricade', 'Someone once built a barricade here. It still mostly stands.'),
    ('an overturned cart', 'An overturned cart has spilled its load across the floor.'),
    ('a broken statue', 'A broken statue lies on its side, big enough to hide behind.'),
    ('a stack of crates', 'A stack of mouldering crates offers decent cover.'),
]

# Pack tactics: each other near melee ally makes an enemy bolder (+1 to hit,
# capped). Breaking the pack up - or Falling Back - strips the bonus.
PACK_TACTICS_CAP = 2

# Morale: a badly hurt survivor of a broken pack may simply run. Fled enemies
# pay a little XP (you broke them) but drop nothing.
MORALE_HP_FRAC = 0.35   # must be below this fraction of max HP...
MORALE_CHANCE = 0.30    # ...and then this is the chance per turn it bolts

# Bosses announce their signature move one round before it lands, so Taking
# Cover or Falling Back in time is a real decision. Keyed by the special.
TELEGRAPHS = {
    'rally': "The {name} draws breath to bellow an order...",
    'drain': "The {name}'s hand begins to rise, and the air goes cold...",
    'web': "The {name}'s abdomen pulses - it is about to spray...",
    'curse': "The {name} starts shaping your name, backwards...",
    'quake': "The {name} raises both fists high over its head...",
    'breath': "The {name} inhales, and keeps inhaling. Take cover!",
}

# A little variety when something dies. {name} is the enemy's name.
KILL_LINES = [
    "The {name} falls!",
    "The {name} drops where it stands!",
    "The {name} crumples with a last snarl!",
    "That was the end of the {name}!",
    "The {name} goes down and stays down!",
]

# --- Companions ---------------------------------------------------------------
# One hired ally who fights beside you. Hired at any shop; gone for good at
# 0 HP. Pure data here; the brain that runs them lives in companions.py.
#
#   hp / per_level  base HP and growth per player level
#   ac              base armour class (grows slowly with your level)
#   atk             added to their to-hit rolls
#   die             their damage die
#   style           'tank' draws attacks, 'striker' focuses the weakest enemy,
#                   'caster' zaps (with a damage type), 'healer' patches you up
#   dmg_type        damage type for resist/vulnerable purposes ('' = plain)
#   hire            base hire price (deeper floors charge more)
COMPANIONS = {
    'sellsword': dict(
        title='Sellsword', hp=16, per_level=5, ac=14, atk=1, die=8,
        style='tank', dmg_type='', hire=45,
        desc='Big, scarred, and cheap by the pound. Wades in and draws attacks '
             'away from you.'),
    'archer': dict(
        title='Archer', hp=11, per_level=4, ac=13, atk=2, die=6,
        style='striker', dmg_type='piercing', hire=50,
        desc='Quiet, patient, never misses twice. Picks off the weakest enemy '
             'from wherever they stand.'),
    'apprentice': dict(
        title='Apprentice', hp=9, per_level=3, ac=12, atk=2, die=8,
        style='caster', dmg_type='fire', hire=55,
        desc='On the run from a tower somewhere. Snaps motes of fire across '
             'the room - bad news for trolls.'),
    'field medic': dict(
        title='Field Medic', hp=12, per_level=4, ac=13, atk=1, die=4,
        style='healer', dmg_type='', hire=50,
        desc='Has sewn worse than you back together. Patches you up when you '
             'are hurting, jabs something sharp when you are not.'),
}
COMPANION_NAMES = ['Bren', 'Sable', 'Odo', 'Wren', 'Marta', 'Kel', 'Ivo',
                   'Tam', 'Rook', 'Essa', 'Corvin', 'Petra', 'Aldous', 'Nix']
COMPANION_HIRE_PER_FLOOR = 12

# --- Adaptive difficulty ------------------------------------------------------
# A quiet dial the dungeon turns from how your last few fights went. Struggle
# (big HP losses, deaths, long slogs) and packs get a little thinner and drops
# a little kinder; cruise and they firm back up. Bounded tight so it nudges
# rather than rescues. Toggle in Settings; the multiplier is saved with the
# character.
ADAPTIVE_MIN = 0.85
ADAPTIVE_MAX = 1.15
ADAPTIVE_STEP = 0.03
ADAPTIVE_WINDOW = 8     # how many recent fights are remembered

# --- Derived tables ----------------------------------------------------------
# Worked out from the tables above so they can never disagree with them.
# Nothing below needs editing by hand.

MUNDANE_WEAPONS = {k for k in WEAPONS if k not in MAGIC_ITEMS and k != 'unarmed strikes'}
MUNDANE_ARMOR = {k for k in ARMOR if k not in MAGIC_ITEMS}
MUNDANE_SHIELDS = {k for k in SHIELDS if k not in MAGIC_ITEMS}

# Everything you can have equipped, mapped to the slot it goes in.
EQUIPPABLE = {}
for _n in WEAPONS:
    EQUIPPABLE[_n] = 'weapon'
for _n in ARMOR:
    EQUIPPABLE[_n] = 'armor'
for _n in SHIELDS:
    EQUIPPABLE[_n] = 'shield'
for _n, _d in MAGIC_ITEMS.items():
    EQUIPPABLE[_n] = _d['slot']
del _n

# Magic items grouped by rarity, for boss drops and deep chests.
MAGIC_BY_RARITY = {}
for _name, _data in MAGIC_ITEMS.items():
    MAGIC_BY_RARITY.setdefault(_data.get('rarity', 'Uncommon'), []).append(_name)
del _name, _data

# Items that are used up and are not gear - used to decide bonus-action cost.
CONSUMABLES = set(ITEM_INFO) - VALUABLES
