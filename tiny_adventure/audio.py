"""Sound synthesis: the chiptune soundtrack and the effect bank.

Nothing here touches the game or its window, so this module can be run on its
own to render the soundtrack.

THE SOUNDTRACK is about 14 minutes, written as six movements that change key
between them (A minor, then up a fourth, then a minor third, then home for the
finale). Each movement is a list of sections, and each section is:

    (melody, chord_progression, octave_shift, drum_pattern, texture_volumes)

The melodies (M_A..M_E) and progressions (P1..P3) are defined once at the top
of compose_music and reused in different combinations - that is what makes it
feel composed rather than looping.

    Rearrange the music ..... the `movements` list in compose_music
    Change the key of one .... the `keys` list beside it
    Change the tempo ......... `eighth` at the top (seconds per eighth note)
    Write a new melody ....... add M_F and use it in a section

TWO PERFORMANCE TRICKS worth preserving if you edit this:

    note caching - the same notes recur thousands of times, so each distinct
    one is rendered once and reused. Without this a 14-minute track takes
    minutes to build instead of ~20 seconds.

    streaming - write_music_file renders one movement at a time and writes it
    straight to disk. Holding the whole track in memory as Python floats would
    cost hundreds of megabytes. It writes to a .part file and renames it only
    when finished, so an interrupted first run cannot leave a corrupt track
    that gets loaded next time.

SOUND EFFECTS are a much simpler affair: SOUND_DEFS lists each one as a series
of (frequency, duration_ms, volume, waveform) notes. Frequency 0 means noise,
which is what impacts are made of.
"""
import os
import math
import random
import wave
import struct
import array

try:
    import winsound  # built into Python on Windows
except ImportError:
    winsound = None  # elsewhere we fall back to the terminal bell


# --- Sound effects -----------------------------------------------------------
# Each effect is a list of notes: (frequency_hz, duration_ms, volume, shape).
# frequency 0 means a burst of noise (good for impacts).
# --- Sound effects -----------------------------------------------------------
# name: [(frequency_hz, duration_ms, volume, waveform), ...]
#
#   frequency   in hertz. 0 means a burst of noise - use it for impacts.
#   duration    milliseconds. Effects should stay short and punchy.
#   volume      0.0 to 1.0.
#   waveform    'square' is bright and chiptune, 'sine' is soft, 'noise' is a hit.
#
# Rising notes read as success, falling as failure. To add an effect, add an
# entry here and call self.play_sound('your_name') from anywhere in the game.
# The WAV is generated automatically on the next run.
SOUND_DEFS = {
    'hit':       [(150, 60, 0.6, 'square'), (0, 50, 0.4, 'noise')],
    'crit':      [(500, 50, 0.5, 'square'), (750, 60, 0.5, 'square'), (1000, 90, 0.5, 'square')],
    'miss':      [(400, 50, 0.3, 'square'), (300, 60, 0.25, 'square'), (220, 70, 0.2, 'square')],
    'enemy_hit': [(110, 120, 0.55, 'square'), (90, 100, 0.45, 'square')],
    'victory':   [(523, 80, 0.4, 'sine'), (659, 80, 0.4, 'sine'), (784, 80, 0.4, 'sine'), (1047, 160, 0.45, 'sine')],
    'death':     [(392, 150, 0.5, 'square'), (330, 150, 0.5, 'square'), (262, 150, 0.5, 'square'), (196, 300, 0.5, 'square')],
    'levelup':   [(523, 70, 0.4, 'sine'), (659, 70, 0.4, 'sine'), (784, 70, 0.4, 'sine'), (659, 70, 0.4, 'sine'), (784, 70, 0.4, 'sine'), (1047, 200, 0.5, 'sine')],
    'coin':      [(988, 40, 0.4, 'sine'), (1319, 120, 0.4, 'sine')],
    'potion':    [(300, 60, 0.35, 'sine'), (400, 60, 0.35, 'sine'), (500, 80, 0.35, 'sine')],
    'spell':     [(880, 40, 0.35, 'sine'), (1100, 40, 0.35, 'sine'), (1320, 40, 0.35, 'sine'), (1760, 80, 0.4, 'sine')],
    'success':   [(660, 80, 0.4, 'sine'), (880, 140, 0.45, 'sine')],
    'fail':      [(200, 90, 0.45, 'square'), (150, 140, 0.4, 'square')],
    'door':      [(160, 70, 0.35, 'square'), (120, 90, 0.3, 'square')],
    'chest':     [(180, 60, 0.5, 'square'), (0, 40, 0.3, 'noise'), (880, 60, 0.3, 'sine'), (1175, 100, 0.35, 'sine')],
    'equip':     [(1200, 30, 0.35, 'square'), (900, 40, 0.3, 'square'), (1400, 60, 0.3, 'square')],
    'dice':      [(0, 25, 0.25, 'noise'), (620, 20, 0.15, 'square'), (0, 25, 0.2, 'noise'), (740, 20, 0.15, 'square'), (0, 30, 0.22, 'noise')],
    'trap_spring': [(1000, 30, 0.4, 'square'), (500, 40, 0.45, 'square'), (0, 70, 0.4, 'noise')],
}


MUSIC_MOVEMENTS = 6


def compose_music(sample_rate=16000, movement=None):
    """Render one movement of the soundtrack as a list of samples.

    Pass movement=0..MUSIC_MOVEMENTS-1 to build one piece at a time (which is how
    write_music_file streams it to disk); movement=None renders the whole thing.
    
"""
    eighth = 0.227  # ~132 bpm

    E2, F2, G2, A2, B2n, C3, D3, E3, F3, G3, A3, B3 = (82.41, 87.31, 98.0, 110.0, 123.47,
                                                       130.81, 146.83, 164.81, 174.61,
                                                       196.0, 220.0, 246.94)
    C4, D4, E4, F4, G4, A4, B4 = 261.63, 293.66, 329.63, 349.23, 392.0, 440.0, 493.88
    C5, D5, E5, F5, G5, A5, B5 = 523.25, 587.33, 659.25, 698.46, 783.99, 880.0, 987.77
    R = None  # rest

    # chord progressions: one (bass_root, (arp triad)) per bar, 8 bars each
    P1 = [(A2, (A3, C4, E4)), (G2, (G3, B3, D4)), (C3, (C4, E4, G4)), (G2, (G3, B3, D4)),
          (A2, (A3, C4, E4)), (F2, (F3, A3, C4)), (D3, (D4, F4, A4)), (E2, (E3, B3, E4))]
    P2 = [(A2, (A3, C4, E4)), (E2, (E3, G3, B3)), (F2, (F3, A3, C4)), (C3, (C4, E4, G4)),
          (D3, (D4, F4, A4)), (A2, (A3, C4, E4)), (E2, (E3, B3, E4)), (E2, (E3, B3, E4))]
    P3 = [(C3, (C4, E4, G4)), (G2, (G3, B3, D4)), (A2, (A3, C4, E4)), (F2, (F3, A3, C4)),
          (C3, (C4, E4, G4)), (G2, (G3, B3, D4)), (F2, (F3, A3, C4)), (E2, (E3, B3, E4))]

    # 8-bar melodies as (note, eighths); every bar sums to 8
    M_A = [(A4,1),(B4,1),(C5,2),(E5,2),(D5,1),(C5,1),
           (B4,2),(G4,1),(B4,1),(D5,3),(R,1),
           (C5,1),(D5,1),(E5,2),(G5,2),(F5,1),(E5,1),
           (D5,2),(B4,1),(G4,1),(B4,3),(R,1),
           (A4,1),(B4,1),(C5,2),(E5,2),(D5,1),(C5,1),
           (F5,2),(E5,1),(D5,1),(C5,3),(R,1),
           (D5,1),(E5,1),(F5,2),(E5,2),(D5,1),(B4,1),
           (A4,6),(R,2)]
    M_B = [(E5,1),(E5,1),(R,1),(E5,1),(G5,2),(E5,2),
           (F5,1),(F5,1),(R,1),(F5,1),(A5,2),(F5,2),
           (G5,2),(E5,2),(C5,2),(E5,2),
           (D5,1),(E5,1),(D5,1),(B4,1),(G4,4),
           (A4,1),(C5,1),(E5,1),(A5,1),(G5,2),(E5,2),
           (F5,2),(C5,2),(A4,2),(C5,2),
           (D5,1),(F5,1),(A5,2),(G5,2),(F5,1),(E5,1),
           (E5,4),(B4,2),(E4,2)]
    M_C = [(E5,2),(D5,1),(C5,1),(B4,2),(A4,2),                     # darker, over P2
           (B4,2),(G4,2),(E4,3),(R,1),
           (A4,1),(C5,1),(F5,2),(E5,2),(C5,2),
           (E5,2),(G5,2),(E5,2),(C5,2),
           (D5,2),(F5,1),(A5,1),(F5,2),(D5,2),
           (C5,2),(E5,2),(A4,3),(R,1),
           (B4,2),(E5,2),(G5,2),(F5,1),(E5,1),
           (B4,4),(E5,2),(E4,2)]
    M_D = [(G5,2),(E5,1),(C5,1),(G4,2),(C5,2),                     # bright bridge, over P3
           (D5,2),(B4,1),(G4,1),(D5,3),(R,1),
           (E5,1),(C5,1),(A4,2),(E5,2),(C5,2),
           (C5,2),(A4,1),(F4,1),(A4,3),(R,1),
           (G5,2),(E5,2),(C5,1),(E5,1),(G5,2),
           (D5,1),(E5,1),(D5,1),(B4,1),(G4,4),
           (F5,2),(A5,2),(F5,2),(C5,2),
           (E5,6),(B4,2)]
    M_E = [(A4,8),                                                  # sparse breakdown, over P1
           (B4,8),
           (C5,6),(E5,2),
           (D5,8),
           (A4,4),(C5,4),
           (C5,8),
           (D5,4),(F5,4),
           (E5,8)]

    # arrangement: (melody or None, progression, lead_shift_semitones, drums, textures)
    # drums: 'none' | 'hats' | 'light' | 'full' | 'groove'
    # The suite is split into movements so the WAV can be rendered (and streamed to
    # disk) a piece at a time instead of holding ~15 minutes of audio in memory.
    movements = [
        # I. Descent - state the main themes in A minor
        [(None, P1, 0, 'none',  dict(arp=0.05, bass=0.2)),         # intro
         (M_A,  P1, 0, 'hats',  {}),
         (M_A,  P1, 0, 'full',  {}),
         (M_B,  P1, 0, 'full',  {}),
         (M_A,  P1, -12, 'full', dict(lead=0.15)),
         (M_C,  P2, 0, 'full',  {}),
         (M_C,  P2, 12, 'light', dict(lead=0.1)),
         (M_D,  P3, 0, 'light', {}),
         (M_E,  P1, 0, 'none',  dict(lead=0.11, arp=0.035)),       # breakdown
         (M_B,  P1, 0, 'full',  {})],

        # II. Deeper halls - reprise with a drum-and-bass break
        [(M_A,  P1, 0, 'full',  {}),
         (M_C,  P2, 0, 'full',  {}),
         (M_D,  P3, 0, 'full',  {}),
         (M_B,  P1, 12, 'full', dict(lead=0.1)),
         (M_A,  P1, 0, 'full',  {}),
         (None, P1[:4], 0, 'groove', dict(arp=0.0, bass=0.22)),    # drum+bass break
         (M_B,  P1, 0, 'full',  {}),
         (M_C,  P2, 0, 'full',  {}),
         (M_D,  P3, 12, 'full', dict(lead=0.1)),                   # soaring bridge
         (M_A,  P1, 0, 'full',  {})],

        # III. The flooded vault - same themes a fourth up (D minor)
        [(None, P1, 0, 'hats',  dict(arp=0.05, bass=0.2)),
         (M_C,  P2, 0, 'light', {}),
         (M_A,  P1, 0, 'full',  {}),
         (M_A,  P1, -12, 'full', dict(lead=0.14)),
         (M_D,  P3, 0, 'full',  {}),
         (M_E,  P1, 0, 'none',  dict(lead=0.1, arp=0.03)),
         (M_B,  P1, 0, 'full',  {}),
         (M_C,  P2, 12, 'light', dict(lead=0.1)),
         (M_D,  P3, 0, 'full',  {}),
         (M_A,  P1, 0, 'full',  {})],

        # IV. Pursuit - driving, mostly full drums
        [(M_B,  P1, 0, 'full',  {}),
         (M_B,  P1, 12, 'full', dict(lead=0.1)),
         (M_A,  P1, 0, 'full',  {}),
         (None, P1[:4], 0, 'groove', dict(arp=0.0, bass=0.22)),
         (M_C,  P2, 0, 'full',  {}),
         (M_D,  P3, 0, 'full',  {}),
         (M_A,  P1, 0, 'full',  {}),
         (M_C,  P2, 0, 'full',  {}),
         (M_D,  P3, 12, 'full', dict(lead=0.1)),
         (M_B,  P1, 0, 'full',  {})],

        # V. The dark below - a minor third up (F minor), sparser and colder
        [(M_E,  P1, 0, 'none',  dict(lead=0.1, arp=0.03)),
         (M_C,  P2, 0, 'light', {}),
         (M_C,  P2, -12, 'light', dict(lead=0.13)),
         (M_A,  P1, 0, 'hats',  {}),
         (M_D,  P3, 0, 'light', {}),
         (M_B,  P1, 0, 'full',  {}),
         (M_A,  P1, 0, 'full',  {}),
         (M_E,  P1, 12, 'none', dict(lead=0.1, arp=0.03)),
         (M_D,  P3, 0, 'full',  {}),
         (M_C,  P2, 0, 'full',  {})],

        # VI. Homecoming - back to A minor for the finale
        [(M_A,  P1, 0, 'hats',  {}),
         (M_A,  P1, 0, 'full',  {}),
         (M_B,  P1, 0, 'full',  {}),
         (M_C,  P2, 0, 'full',  {}),
         (M_D,  P3, 12, 'full', dict(lead=0.1)),
         (M_B,  P1, 12, 'full', dict(lead=0.1)),
         (M_A,  P1, 0, 'full',  {}),                               # final full chorus
         (M_A,  P1, -12, 'hats', dict(lead=0.12)),                 # winding down
         (M_E,  P1, 0, 'none',  dict(lead=0.09, arp=0.04)),        # outro
         (None, P1, 0, 'none',  dict(arp=0.04, bass=0.16))],
    ]
    # each movement is played in this key (semitones from A minor)
    keys = [0, 0, 5, 5, 8, 0]

    if movement is None:
        sections = [s for mv in movements for s in mv]
        key_shift = 0
    else:
        sections = movements[movement % len(movements)]
        key_shift = keys[movement % len(keys)]

    n_eighth = int(sample_rate * eighth)
    total_bars = sum(len(p) for (_m, p, _s, _d, _t) in sections)
    total = total_bars * 8 * n_eighth
    mix = array.array('d', bytes(8 * total))
    two_pi = 2 * math.pi
    uniform = random.uniform
    key_ratio = 2.0 ** (key_shift / 12.0)

    # The same handful of notes recur thousands of times across a long suite,
    # so each distinct one is rendered once and then simply mixed in again.
    note_cache = {}

    def render_note(freq, dur_s, shape, vol, vibrato):
        n = max(1, int(sample_rate * dur_s))
        atk = int(sample_rate * 0.006)
        rel = int(sample_rate * 0.012)
        inv_n = 1.0 / n
        buf = array.array('d', bytes(8 * n))
        for kk in range(n):
            t = kk / sample_rate
            f = freq * (1.0 + 0.006 * math.sin(two_pi * 5.5 * t)) if vibrato else freq
            ph = (t * f) % 1.0
            if shape == 'pulse25':
                v = 1.0 if ph < 0.25 else -1.0
            elif shape == 'triangle':
                v = 4.0 * abs(ph - 0.5) - 1.0
            elif shape == 'noise':
                v = uniform(-1.0, 1.0)
            elif shape == 'sine':
                v = math.sin(two_pi * f * t)
            else:
                v = 1.0 if ph < 0.5 else -1.0
            env = 1.0 - kk * inv_n * 0.5
            if kk < atk:
                env *= kk / max(1, atk)
            if kk > n - rel:
                env *= (n - kk) / max(1, rel)
            buf[kk] = v * env * vol
        return buf

    def add_note(start, freq, dur_s, shape, vol, vibrato=False):
        freq = freq * key_ratio
        ckey = (round(freq, 3), round(dur_s, 5), shape, round(vol, 4), vibrato)
        # Cache hit or miss: identical notes recur thousands of times across the
        # suite, so rendering each once is what keeps generation to ~20 seconds
        # rather than several minutes.
        buf = note_cache.get(ckey)
        if buf is None:
            buf = render_note(freq, dur_s, shape, vol, vibrato)
            if shape != 'noise':  # noise should differ every time
                note_cache[ckey] = buf
        n = len(buf)
        if start + n > total:
            n = total - start
        for kk in range(n):
            mix[start + kk] += buf[kk]

    shift_cache = {}

    def shifted(freq, semis):
        if semis == 0:
            return freq
        key = (freq, semis)
        if key not in shift_cache:
            shift_cache[key] = freq * (2.0 ** (semis / 12.0))
        return shift_cache[key]

    bar_offset = 0
    for melody, prog, lead_shift, drums, tex in sections:
        lead_vol = tex.get('lead', 0.13)
        arp_vol = tex.get('arp', 0.055)
        bass_vol = tex.get('bass', 0.2)
        # lead
        if melody is not None:
            pos = bar_offset * 8 * n_eighth
            for freq, ln in melody:
                if freq is not None:
                    add_note(pos, shifted(freq, lead_shift), ln * eighth * 0.96,
                             'pulse25', lead_vol, vibrato=(ln >= 2))
                pos += ln * n_eighth
        # arp + bass follow the progression
        for b, (root, triad) in enumerate(prog):
            r3, t3, f3 = triad
            arp_pat = [r3, t3, f3, t3, r3, t3, f3, t3]
            bass_pat = [root, root, root * 1.5, root, root * 2, root, root * 1.5, root]
            base = (bar_offset + b) * 8 * n_eighth
            for e in range(8):
                if arp_vol > 0:
                    add_note(base + e * n_eighth, arp_pat[e], eighth * 0.9, 'square', arp_vol)
                add_note(base + e * n_eighth, bass_pat[e], eighth * 0.85, 'triangle', bass_vol)
        # drums
        if drums != 'none':
            for b in range(len(prog)):
                for e in range(8):
                    start = ((bar_offset + b) * 8 + e) * n_eighth
                    if drums in ('full', 'groove', 'light') and e == 0:
                        add_note(start, 62, 0.1, 'sine', 0.3)
                    if drums in ('full', 'groove') and e == 4:
                        add_note(start, 0, 0.07, 'noise', 0.11)
                    if drums in ('full', 'groove', 'hats', 'light'):
                        add_note(start, 0, 0.022, 'noise', 0.045)
                    if drums == 'groove' and e in (3, 6):
                        add_note(start, 62, 0.08, 'sine', 0.2)
        bar_offset += len(prog)

    return [s / (1.0 + abs(s) * 0.35) for s in mix]


def write_music_file(path, sample_rate=16000, progress=None):
    """Render the whole soundtrack to a WAV file, one movement at a time.

    Streaming keeps peak memory to a couple of minutes of audio rather than the
    full quarter hour. `progress` is called with (done, total) as each movement
    finishes, which is what drives the 'composing...' messages in the log.
    
"""
    # Written under a temporary name and only renamed when complete, so an
    # interrupted first run cannot leave a corrupt track to be loaded later.
    tmp = path + '.part'
    with wave.open(tmp, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for mv in range(MUSIC_MOVEMENTS):
            samples = compose_music(sample_rate, movement=mv)
            w.writeframes(b''.join(struct.pack('<h', int(s * 32767)) for s in samples))
            del samples
            if progress:
                try:
                    progress(mv + 1, MUSIC_MOVEMENTS)
                except Exception:
                    pass
    # only publish the finished file so a half-written track is never opened
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    os.replace(tmp, path)


class MciAudio:
    """Windows MCI wrapper so music and sound effects can play at the same time
    (winsound can only play one sound at once). Silently inert elsewhere.
"""

    def __init__(self):
        """Try to reach the Windows audio interface; stay inert if it is absent."""
        self.ok = False
        try:
            import ctypes
            self._send = ctypes.windll.winmm.mciSendStringW
            self.ok = True
        except Exception:
            self._send = None

    def cmd(self, s):
        """Send one MCI command string. Does nothing on non-Windows systems."""
        if not self.ok:
            return
        try:
            self._send(s, None, 0, None)
        except Exception:
            pass

    def set_volume(self, alias, percent):
        """Set an alias' volume. MCI takes 0-1000; we take a friendly 0-100."""
        level = max(0, min(1000, int(round(percent * 10))))
        self.cmd(f'setaudio {alias} volume to {level}')


def synth_note(freq, dur_ms, volume, shape, sample_rate=22050):
    """Generate one note as a list of float samples in [-1, 1] with a fade-out."""
    n = max(1, int(sample_rate * dur_ms / 1000))
    samples = []
    for i in range(n):
        t = i / sample_rate
        envelope = 1.0 - (i / n)  # linear fade-out so notes don't click
        if freq <= 0 or shape == 'noise':
            value = random.uniform(-1.0, 1.0)
        elif shape == 'square':
            value = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        else:  # sine
            value = math.sin(2 * math.pi * freq * t)
        samples.append(value * envelope * volume)
    return samples


def write_sound_file(path, notes, sample_rate=22050):
    """Write a sequence of notes to a 16-bit mono WAV file."""
    samples = []
    for freq, dur_ms, volume, shape in notes:
        samples.extend(synth_note(freq, dur_ms, volume, shape, sample_rate))
    with wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = b''.join(
            struct.pack('<h', int(max(-1.0, min(1.0, s)) * 32767)) for s in samples
        )
        w.writeframes(frames)
