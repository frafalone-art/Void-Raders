"""
snippets.py — Void Raiders

A curated collection of pieces from the full Void Raiders codebase that I'm
particularly happy with. This is NOT the full game (which stays private) —
just excerpts kept here for demonstration, showing a few techniques used
throughout the project: inheritance hierarchies, vector-based steering AI,
finite state machines, rule-based procedural generation, probability-driven
enemy behavior, and procedural audio synthesis.

Some snippets reference other modules (settings, sprites, player) that
aren't included here — they're excerpted for readability, not meant to run
standalone. The playable game is on itch.io:
https://francescofalone.itch.io/void-raiders
"""

import math
import random
import array
import pygame


# =============================================================================
# 1) INHERITANCE — a common base class for all 10 enemy types, each
#    overriding only what actually differs (hp, sprite, color, behavior).
# =============================================================================

class Invader(pygame.sprite.Sprite):
    """Common base for all enemy types. _redraw() darkens the sprite based
    on remaining HP — visual damage feedback without needing health bars."""
    drop_prob = 0.08  # overridden by tougher subclasses

    def __init__(self, col, row):
        super().__init__()
        self.hp = self.hp_max
        w, h = getattr(self, "_img_w", 48), getattr(self, "_img_h", 32)
        self.rect = pygame.Rect(col * 60, row * 50, w, h)
        self._redraw()

    def _redraw(self):
        t = max(0.25, self.hp / self.hp_max)
        col = tuple(int(c * t) for c in self.color)
        # ... draws self.bmp in `col` onto self.image (omitted here)

    def take_damage(self, amount=1):
        self.hp -= amount
        self._redraw()
        return self.hp <= 0


class WeakInvader(Invader):
    """The whole class body is just its stats — everything else comes free
    from Invader."""
    hp_max = 1
    points = 10
    color = (0, 220, 255)
    shoot_prob = 0.004


class TankInvader(Invader):
    hp_max = 5
    points = 30
    color = (220, 50, 255)
    drop_prob = 0.15  # tougher enemies drop powerups more often


# =============================================================================
# 2) MIXIN + VECTOR-BASED AI — dive/return steering shared by multiple
#    enemy types (FastInvader, BeeInvader), added via composition instead
#    of forcing them into a single rigid inheritance branch.
# =============================================================================

class DiveMixin:
    """Mixin: adds dive/return behavior to any Invader subclass without
    forcing a shared base class. Classes that use it call init_dive() in
    their own __init__."""
    FORMATION = "formation"
    DIVING = "diving"
    RETURNING = "returning"

    def init_dive(self):
        self.state = self.FORMATION
        self.home = pygame.Vector2(self.rect.x, self.rect.y)
        self.dive_target = None

    def start_dive(self, player_rect):
        self.state = self.DIVING
        self.dive_target = pygame.Vector2(player_rect.centerx, player_rect.centery)

    def update_dive(self):
        """Steering via pygame.Vector2: normalize the direction to the
        target, scale it to the enemy's speed, move by that amount every
        frame. Same idea for diving toward the player and returning home."""
        pos = pygame.Vector2(self.rect.center)
        spd_dive = getattr(self, "DIVE_SPD", 5)
        spd_ret = getattr(self, "RETURN_SPD", 3)

        if self.state == self.DIVING:
            d = self.dive_target - pos
            if d.length() < spd_dive + 2:
                self.state = self.RETURNING
                return False
            d.scale_to_length(spd_dive)
            self.rect.x += int(d.x)
            self.rect.y += int(d.y)

        elif self.state == self.RETURNING:
            d = self.home - pos
            if d.length() < spd_ret + 2:
                self.rect.x, self.rect.y = int(self.home.x), int(self.home.y)
                self.state = self.FORMATION
                return True
            d.scale_to_length(spd_ret)
            self.rect.x += int(d.x)
            self.rect.y += int(d.y)
        return False


class FastInvader(DiveMixin, Invader):
    """Multiple inheritance in action: FastInvader IS an Invader (sprite,
    hp, damage) AND gets dive/return steering from DiveMixin — no
    duplicated logic between it and BeeInvader, which uses the same mixin."""
    hp_max = 2
    points = 20
    color = (255, 220, 40)
    DIVE_SPD = 6
    RETURN_SPD = 3

    def __init__(self, col, row):
        super().__init__(col, row)
        self.init_dive()


# =============================================================================
# 3) FINITE STATE MACHINE — boss AI. Simplified excerpt from DashBoss:
#    ROAM -> WINDUP -> CHARGE -> RETURN -> RECOVER, with a phase-2 that
#    reads the boss's own HP to get faster and more aggressive.
# =============================================================================

class DashBoss:
    """FSM: ROAM -> WINDUP -> CHARGE -> RETURN -> RECOVER.
    Phase 2 kicks in at half HP: faster roam, randomized dash, shoots more."""
    ROAM, WINDUP, CHARGE, RETURN, RECOVER = "roam", "windup", "charge", "return", "recover"
    hp_max = 20

    def __init__(self):
        self.hp = self.hp_max
        self.state = self.ROAM
        self.state_timer = 0
        self.phase2 = False
        self.pos = pygame.Vector2(0, 0)
        self.target = pygame.Vector2(0, 0)
        self.charge_vec = None

    # Parameters read live from self.phase2 — no separate "phase 2 class",
    # just properties that change behavior based on current state.
    @property
    def _roam_spd(self):
        return 5.0 if self.phase2 else 2.8

    @property
    def _charge_spd(self):
        return 17.0 if self.phase2 else 13.0

    def update(self, player_pos, dt):
        self.state_timer += dt

        if not self.phase2 and self.hp <= self.hp_max // 2:
            self.phase2 = True  # boss "levels up" mid-fight based on damage taken

        if self.state == self.ROAM:
            d = self.target - self.pos
            if d.length() < 4:
                self.state = self.WINDUP
                self.state_timer = 0
            else:
                d.scale_to_length(self._roam_spd)
                self.pos += d

        elif self.state == self.WINDUP:
            # flashes yellow here (handled by the renderer) to telegraph
            # the incoming dash — gives the player a fair warning window
            if self.state_timer > (300 if self.phase2 else 600):
                self.charge_vec = (player_pos - self.pos).normalize()
                self.state = self.CHARGE
                self.state_timer = 0

        elif self.state == self.CHARGE:
            self.pos += self.charge_vec * self._charge_spd
            if self.state_timer > 500:
                self.state = self.RETURN
                self.state_timer = 0

        elif self.state == self.RETURN:
            d = pygame.Vector2(0, 55) - self.pos
            if d.length() < self._roam_spd + 2:
                self.state = self.RECOVER
                self.state_timer = 0
            else:
                d.scale_to_length(self._roam_spd)
                self.pos += d

        elif self.state == self.RECOVER:
            # boss is vulnerable here — a fair "punish window" after the dash
            if self.state_timer > 400:
                self.state = self.ROAM


# =============================================================================
# 4) RULE-BASED PROCEDURAL GENERATION — endless-mode enemy formations.
#    Instead of random noise, enemies are picked from mutually-exclusive
#    groups so every generated wave stays readable and fair.
# =============================================================================

_GROUP_FRONT = ["TankInvader", "HiveInvader", "ShieldCarrier"]      # pick 1
_GROUP_DIVER = ["FastInvader", "BeeInvader"]                        # pick 1
_GROUP_BACK = ["SplitterInvader", "WeakInvader", "AimShooter", "TeleporterInvader"]  # pick 1
_KAMIKAZE_CAP = 5

def generate_endless_formation(wave: int, rng: random.Random):
    """Builds one wave's enemy roster respecting exclusion rules (e.g. a
    Hive can't share the field with a Fast diver, since a Hive's job is to
    keep the field crowded and Fast divers already do that alone), with
    density and variety both increasing as `wave` grows."""
    front = rng.choice(_GROUP_FRONT)

    diver_pool = list(_GROUP_DIVER)
    if front == "HiveInvader":
        diver_pool.remove("FastInvader")  # Hive + Fast would overload the field
    diver = rng.choice(diver_pool)

    back = rng.choice(_GROUP_BACK)

    # Kamikaze is an optional 4th type, capped and increasingly likely
    # on later waves — but never more than _KAMIKAZE_CAP per wave.
    kamikaze_chance = min(0.75, 0.15 + wave * 0.02)
    has_kamikaze = rng.random() < kamikaze_chance

    return {
        "front": front,
        "diver": diver,
        "back": back,
        "kamikaze": has_kamikaze,
        "kamikaze_cap": _KAMIKAZE_CAP,
        "density": min(1.0, 0.35 + wave * 0.025),  # fills every possible slot eventually
    }


# =============================================================================
# 5) PROCEDURAL AUDIO — every sound effect is synthesized at runtime with
#    stdlib `array` + `math`, no external audio files at all.
# =============================================================================

def make_sound(freq: float, ms: int, vol: float = 0.18,
                shape: str = "sine", attack_ms: int = 8) -> pygame.mixer.Sound:
    """Generates a mono 16-bit sound buffer sample by sample.
    shape: 'sine' | 'square' | 'saw' | 'noise'."""
    rate = 22050
    n = int(rate * ms / 1000)
    attack = int(rate * attack_ms / 1000)
    buf = array.array("h")

    for i in range(n):
        t = i / rate
        envelope = min(i / max(attack, 1), 1.0) * ((n - i) / n)  # fade in/out

        if shape == "sine":
            v = math.sin(2 * math.pi * freq * t)
        elif shape == "square":
            v = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        elif shape == "saw":
            v = 2 * ((freq * t) % 1) - 1
        else:  # noise
            v = random.uniform(-1, 1)

        sample = int(max(-32767, min(32767, v * envelope * vol * 32767)))
        buf.append(sample)

    return pygame.mixer.Sound(buffer=buf)


# =============================================================================
# 6) PROBABILITY-BASED ENEMY BEHAVIOR — the ShieldCarrier blocks any
#    incoming shot with a flat chance instead of a scripted invincibility
#    window, keeping every hit meaningful without making the fight feel
#    like a rhythm-game "wait for the flash" gimmick.
# =============================================================================

class ShieldCarrier(Invader):
    """Every shot has a 25% chance of being absorbed by the shield — no
    damage, no destroyed bullet exception. Two weapon types get a special
    interaction on top of that roll:
      - a piercing shot (sniper) still rolls the same 25%, but on a miss
        it keeps traveling through, since piercing is its whole identity
      - a bouncing shot always ricochets onward regardless of the roll,
        it just doesn't deal damage on a block
    """
    hp_max = 3
    points = 60
    color = (80, 200, 255)
    BLOCK_CHANCE = 0.25

    def handle_bouncer(self, bullet) -> bool:
        """Only ever called for the bouncing weapon. Guards against the
        same bullet re-triggering this on consecutive frames while it's
        still overlapping the shield (its redirect only changes velocity,
        not position, so the overlap can persist for a frame or two) —
        without the hit_set check below, a single pass could burn through
        every bounce the projectile has in one spot."""
        hit_set = getattr(bullet, "hit_set", None)
        if hit_set is not None and id(self) in hit_set:
            return False
        if random.random() >= self.BLOCK_CHANCE:
            self.take_damage(getattr(bullet, "damage", 1))
        bullet.on_bouncer_hit(self)  # ricochets either way
        return True
