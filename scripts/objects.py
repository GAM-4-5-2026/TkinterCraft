import math

AIR, GRASS, DIRT, STONE, SAND, LOG, LEAVES, BEDROCK, COBBLESTONE, PLANKS, BRICKS = range(11)


class Block:

    def __init__(self, name, side, top=None, bottom=None, texture=0.12, strip=False):
        self.name = name
        self.side = side
        self.top = top or side
        self.bottom = bottom or side
        # koliko je "tekstura" (sum svjetline) izrazena na bloku
        self.texture = texture
        # trava ima zeleni rub na vrhu bocnih strana
        self.strip = strip


BLOCKS = [
    None,
    Block("grass", side=(134, 96, 67), top=(106, 190, 48), texture=0.10, strip=True),
    Block("dirt", side=(134, 96, 67), texture=0.12),
    Block("stone", side=(140, 140, 140), texture=0.16),
    Block("sand", side=(219, 207, 142), texture=0.08),
    Block("log", side=(110, 84, 50), top=(176, 142, 90), texture=0.18),
    Block("leaves", side=(58, 150, 40), texture=0.30),
    Block("bedrock", side=(85, 85, 85), texture=0.30),
    Block("cobblestone", side=(120, 120, 120), texture=0.35),
    Block("planks", side=(170, 132, 80), texture=0.14),
    Block("bricks", side=(160, 75, 60), texture=0.22),
]

# blokovi koje igrac moze postavljati (tipke 1-9)
HOTBAR = [GRASS, DIRT, STONE, COBBLESTONE, PLANKS, LOG, LEAVES, SAND, BRICKS]


class Entity:

    def __init__(self, name, position=(0.0, 0.0, 0.0)):
        self.name = name
        self.x, self.y, self.z = position
        self.vx = self.vy = self.vz = 0.0


class Player(Entity):
    HALF_WIDTH = 0.3
    HEIGHT = 1.8
    EYE_HEIGHT = 1.62
    WALK_SPEED = 4.3
    SPRINT_SPEED = 5.6
    JUMP_SPEED = 8.4
    GRAVITY = 28.0
    MAX_FALL = 50.0
    EPS = 1e-3

    def __init__(self, position):
        super().__init__("player", position)
        self.yaw = 0.0
        self.pitch = 0.0
        self.on_ground = False

    def look(self, dyaw, dpitch):
        self.yaw = (self.yaw + dyaw) % (2 * math.pi)
        self.pitch = max(-1.55, min(1.55, self.pitch + dpitch))

    def camera(self):
        return self.x, self.y + self.EYE_HEIGHT, self.z, self.yaw, self.pitch

    def look_direction(self):
        cos_p = math.cos(self.pitch)
        return cos_p * math.sin(self.yaw), math.sin(self.pitch), cos_p * math.cos(self.yaw)

    def overlaps(self, bx, by, bz):
        return (bx < self.x + self.HALF_WIDTH and bx + 1 > self.x - self.HALF_WIDTH
                and by < self.y + self.HEIGHT and by + 1 > self.y
                and bz < self.z + self.HALF_WIDTH and bz + 1 > self.z - self.HALF_WIDTH)

    def update(self, dt, keys, world):
        forward = ("w" in keys) - ("s" in keys)
        strafe = ("d" in keys) - ("a" in keys)
        sin_y, cos_y = math.sin(self.yaw), math.cos(self.yaw)
        mx = sin_y * forward + cos_y * strafe
        mz = cos_y * forward - sin_y * strafe
        length = math.hypot(mx, mz)
        sprint = "shift_l" in keys or "shift_r" in keys
        if length:
            speed = (self.SPRINT_SPEED if sprint else self.WALK_SPEED) / length
            mx, mz = mx * speed, mz * speed

        # u zraku se smjer mijenja sporije nego na tlu
        k = min(1.0, dt * (14.0 if self.on_ground else 3.0))
        self.vx += (mx - self.vx) * k
        self.vz += (mz - self.vz) * k

        if "space" in keys and self.on_ground:
            self.vy = self.JUMP_SPEED
            self.on_ground = False

        steps = max(1, math.ceil(dt / 0.02))
        h = dt / steps
        for _ in range(steps):
            self.vy = max(-self.MAX_FALL, self.vy - self.GRAVITY * h)
            self._move_x(world, self.vx * h)
            self._move_z(world, self.vz * h)
            self._move_y(world, self.vy * h)

        top = world.height - self.HEIGHT - 1
        if self.y > top:
            self.y, self.vy = top, 0.0

    def _blocked(self, world, xs, ys, zs):
        for x in xs:
            for y in ys:
                for z in zs:
                    if world.is_solid(x, y, z):
                        return True
        return False

    def _span(self, lo, hi):
        return range(math.floor(lo), math.floor(hi - 1e-6) + 1)

    def _move_x(self, world, d):
        if not d:
            return
        x = self.x + d
        edge = math.floor(x + self.HALF_WIDTH if d > 0 else x - self.HALF_WIDTH)
        ys = self._span(self.y, self.y + self.HEIGHT)
        zs = self._span(self.z - self.HALF_WIDTH, self.z + self.HALF_WIDTH)
        if self._blocked(world, (edge,), ys, zs):
            x = edge - self.HALF_WIDTH - self.EPS if d > 0 else edge + 1 + self.HALF_WIDTH + self.EPS
            self.vx = 0.0
        self.x = x

    def _move_z(self, world, d):
        if not d:
            return
        z = self.z + d
        edge = math.floor(z + self.HALF_WIDTH if d > 0 else z - self.HALF_WIDTH)
        xs = self._span(self.x - self.HALF_WIDTH, self.x + self.HALF_WIDTH)
        ys = self._span(self.y, self.y + self.HEIGHT)
        if self._blocked(world, xs, ys, (edge,)):
            z = edge - self.HALF_WIDTH - self.EPS if d > 0 else edge + 1 + self.HALF_WIDTH + self.EPS
            self.vz = 0.0
        self.z = z

    def _move_y(self, world, d):
        self.on_ground = False
        if not d:
            return
        y = self.y + d
        edge = math.floor(y + self.HEIGHT if d > 0 else y)
        xs = self._span(self.x - self.HALF_WIDTH, self.x + self.HALF_WIDTH)
        zs = self._span(self.z - self.HALF_WIDTH, self.z + self.HALF_WIDTH)
        if self._blocked(world, xs, (edge,), zs):
            if d > 0:
                y = edge - self.HEIGHT - self.EPS
            else:
                y = edge + 1
                self.on_ground = True
            self.vy = 0.0
        self.y = y
