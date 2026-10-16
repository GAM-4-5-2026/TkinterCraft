import math

AIR = 0
GRASS = 1
DIRT = 2
STONE = 3
SAND = 4
LOG = 5
LEAVES = 6
BEDROCK = 7
COBBLESTONE = 8
PLANKS = 9
BRICKS = 10
LUCKY = 11
TNT = 12
COAL_ORE = 13
GOLD_ORE = 14
DIAMOND_ORE = 15
GOLD_BLOCK = 16
DIAMOND_BLOCK = 17
SKY_LUCKY = 18


class Block:

    def __init__(self, name, side, top=None, bottom=None, texture=0.12, strip=False,
                 speck=None, char=None, glow=False, points=0):
        self.name = name
        self.side = side
        if top is None:
            top = side
        if bottom is None:
            bottom = side
        self.top = top
        self.bottom = bottom
        self.texture = texture
        self.strip = strip
        self.speck = speck
        self.char = char
        self.glow = glow
        self.points = points


# svi blokovi, redoslijed mora bit isti kao brojevi gore
BLOCKS = [
    None,
    Block("trava", side=(134, 96, 67), top=(106, 190, 48), texture=0.10, strip=True),
    Block("zemlja", side=(134, 96, 67), texture=0.12),
    Block("kamen", side=(140, 140, 140), texture=0.16),
    Block("pijesak", side=(219, 207, 142), texture=0.08),
    Block("deblo", side=(110, 84, 50), top=(176, 142, 90), texture=0.18),
    Block("lisce", side=(58, 150, 40), texture=0.30),
    Block("bedrock", side=(85, 85, 85), texture=0.30),
    Block("kaldrma", side=(120, 120, 120), texture=0.35),
    Block("daske", side=(170, 132, 80), texture=0.14),
    Block("cigle", side=(160, 75, 60), texture=0.22),
    Block("lucky blok", side=(250, 195, 20), texture=0.08, char="?", glow=True),
    Block("TNT", side=(215, 45, 35), top=(225, 215, 200), texture=0.1, char="!", glow=True),
    Block("ugljen", side=(140, 140, 140), texture=0.16, speck=(25, 25, 25), points=2),
    Block("zlatna ruda", side=(140, 140, 140), texture=0.16, speck=(255, 205, 40), points=10),
    Block("dijamant", side=(140, 140, 140), texture=0.16, speck=(70, 235, 235), points=25),
    Block("zlatni blok", side=(250, 210, 60), texture=0.12, points=5),
    Block("dijamantni blok", side=(110, 235, 235), texture=0.12, points=15),
    Block("nebeski lucky blok", side=(185, 120, 255), texture=0.08, char="?", glow=True),
]

LUCKY_BLOCKS = (LUCKY, SKY_LUCKY)

HOTBAR = [GRASS, DIRT, STONE, COBBLESTONE, PLANKS, LOG, LEAVES, SAND, BRICKS]


class Player:
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
        self.x = position[0]
        self.y = position[1]
        self.z = position[2]
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self.yaw = 0.0
        self.pitch = 0.0
        self.on_ground = False
        self.effects = {}

    def look(self, dyaw, dpitch):
        self.yaw = (self.yaw + dyaw) % (2 * math.pi)
        self.pitch = max(-1.55, min(1.55, self.pitch + dpitch))

    def camera(self):
        return self.x, self.y + self.EYE_HEIGHT, self.z, self.yaw, self.pitch

    def look_direction(self):
        cos_p = math.cos(self.pitch)
        return cos_p * math.sin(self.yaw), math.sin(self.pitch), cos_p * math.cos(self.yaw)

    def overlaps(self, bx, by, bz):
        if bx >= self.x + self.HALF_WIDTH or bx + 1 <= self.x - self.HALF_WIDTH:
            return False
        if by >= self.y + self.HEIGHT or by + 1 <= self.y:
            return False
        if bz >= self.z + self.HALF_WIDTH or bz + 1 <= self.z - self.HALF_WIDTH:
            return False
        return True

    def fits(self, world, y):
        xs = self.span(self.x - self.HALF_WIDTH, self.x + self.HALF_WIDTH)
        zs = self.span(self.z - self.HALF_WIDTH, self.z + self.HALF_WIDTH)
        ys = self.span(y, y + self.HEIGHT)
        return not self.blocked(world, xs, ys, zs)

    def update(self, dt, keys, world):
        forward = 0
        if "w" in keys:
            forward += 1
        if "s" in keys:
            forward -= 1
        strafe = 0
        if "d" in keys:
            strafe += 1
        if "a" in keys:
            strafe -= 1

        sin_y = math.sin(self.yaw)
        cos_y = math.cos(self.yaw)
        mx = sin_y * forward + cos_y * strafe
        mz = cos_y * forward - sin_y * strafe
        length = math.hypot(mx, mz)
        sprint = "shift_l" in keys or "shift_r" in keys

        for name in list(self.effects):
            self.effects[name] -= dt
            if self.effects[name] <= 0:
                del self.effects[name]

        if length:
            if sprint:
                speed = self.SPRINT_SPEED / length
            else:
                speed = self.WALK_SPEED / length
            if "speed" in self.effects:
                speed *= 1.9
            mx = mx * speed
            mz = mz * speed

        if self.on_ground:
            k = min(1.0, dt * 14.0)
        else:
            k = min(1.0, dt * 3.0)
        self.vx += (mx - self.vx) * k
        self.vz += (mz - self.vz) * k

        if "space" in keys and self.on_ground:
            if "jump" in self.effects:
                self.vy = self.JUMP_SPEED * 1.6
            else:
                self.vy = self.JUMP_SPEED * 1.0
            self.on_ground = False

        # fizika u malim koracima inace propadne kroz blokove
        steps = max(1, math.ceil(dt / 0.02))
        h = dt / steps
        for i in range(steps):
            self.vy = max(-self.MAX_FALL, self.vy - self.GRAVITY * h)
            self.move_x(world, self.vx * h)
            self.move_z(world, self.vz * h)
            self.move_y(world, self.vy * h)

        top = world.height - self.HEIGHT - 1
        if self.y > top:
            self.y = top
            self.vy = 0.0

    def blocked(self, world, xs, ys, zs):
        for x in xs:
            for y in ys:
                for z in zs:
                    if world.is_solid(x, y, z):
                        return True
        return False

    def span(self, lo, hi):
        return range(math.floor(lo), math.floor(hi - 1e-6) + 1)

    def move_x(self, world, d):
        if not d:
            return
        x = self.x + d
        if d > 0:
            edge = math.floor(x + self.HALF_WIDTH)
        else:
            edge = math.floor(x - self.HALF_WIDTH)
        ys = self.span(self.y, self.y + self.HEIGHT)
        zs = self.span(self.z - self.HALF_WIDTH, self.z + self.HALF_WIDTH)
        if self.blocked(world, [edge], ys, zs):
            if d > 0:
                x = edge - self.HALF_WIDTH - self.EPS
            else:
                x = edge + 1 + self.HALF_WIDTH + self.EPS
            self.vx = 0.0
        self.x = x

    def move_z(self, world, d):
        if not d:
            return
        z = self.z + d
        if d > 0:
            edge = math.floor(z + self.HALF_WIDTH)
        else:
            edge = math.floor(z - self.HALF_WIDTH)
        xs = self.span(self.x - self.HALF_WIDTH, self.x + self.HALF_WIDTH)
        ys = self.span(self.y, self.y + self.HEIGHT)
        if self.blocked(world, xs, ys, [edge]):
            if d > 0:
                z = edge - self.HALF_WIDTH - self.EPS
            else:
                z = edge + 1 + self.HALF_WIDTH + self.EPS
            self.vz = 0.0
        self.z = z

    def move_y(self, world, d):
        self.on_ground = False
        if not d:
            return
        y = self.y + d
        if d > 0:
            edge = math.floor(y + self.HEIGHT)
        else:
            edge = math.floor(y)
        xs = self.span(self.x - self.HALF_WIDTH, self.x + self.HALF_WIDTH)
        zs = self.span(self.z - self.HALF_WIDTH, self.z + self.HALF_WIDTH)
        if self.blocked(world, xs, [edge], zs):
            if d > 0:
                y = edge - self.HEIGHT - self.EPS
            else:
                y = edge + 1
                self.on_ground = True
            self.vy = 0.0
        self.y = y
