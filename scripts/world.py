import base64
import math
import random
import zlib

from objects import AIR, GRASS, DIRT, STONE, SAND, LOG, LEAVES, BEDROCK
from objects import COAL_ORE, GOLD_ORE, DIAMOND_ORE, GOLD_BLOCK, DIAMOND_BLOCK, SKY_LUCKY


# value noise za brda, na netu pise da je slicno ko perlin
def value_noise(rng, width, depth, cell):
    gw = width // cell + 2
    gd = depth // cell + 2
    grid = []
    for i in range(gw * gd):
        grid.append(rng.random())

    xs_cell = []
    xs_t = []
    for x in range(width):
        gx = x // cell
        t = (x % cell) / cell
        xs_cell.append(gx)
        xs_t.append(t * t * (3 - 2 * t))

    out = []
    for z in range(depth):
        gz = z // cell
        tz = (z % cell) / cell
        tz = tz * tz * (3 - 2 * tz)
        col = []
        for gx in range(gw):
            a = grid[gz * gw + gx]
            b = grid[(gz + 1) * gw + gx]
            col.append(a + (b - a) * tz)
        for x in range(width):
            gx = xs_cell[x]
            out.append(col[gx] + (col[gx + 1] - col[gx]) * xs_t[x])
    return out


def world_from_message(message):
    w = int(message["width"])
    d = int(message["depth"])
    h = int(message["height"])
    blocks = zlib.decompress(base64.b64decode(message["blocks"]))
    if len(blocks) != w * d * h:
        raise ValueError("krivi podaci o svijetu")
    return World(w, d, h, int(message["seed"]), blocks)


class World:
    SAND_LEVEL = 13
    ROCK_LEVEL = 36

    def __init__(self, width=512, depth=512, height=64, seed=None, blocks=None):
        self.width = width
        self.depth = depth
        self.height = height
        if seed is None:
            self.seed = random.randrange(2 ** 30)
        else:
            self.seed = seed
        self.treasures = []
        if blocks is not None:
            self.blocks = bytearray(blocks)
            self.ceiling = self.find_ceiling()
            return
        self.blocks = bytearray(width * depth * height)
        rng = random.Random(self.seed)
        self.make_terrain(rng)
        self.make_ores(rng)
        self.make_boulders(rng)
        self.make_trees(rng)
        self.make_islands(rng)

    def to_message(self):
        data = base64.b64encode(zlib.compress(bytes(self.blocks))).decode("ascii")
        return {"width": self.width, "depth": self.depth, "height": self.height,
                "seed": self.seed, "blocks": data}

    def find_ceiling(self):
        wd = self.width * self.depth
        y = self.height - 1
        while y >= 0:
            layer = self.blocks[y * wd:(y + 1) * wd]
            if layer.count(0) < wd:
                return y + 1
            y -= 1
        return 0

    def index(self, x, y, z):
        return x + z * self.width + y * self.width * self.depth

    def inside(self, x, y, z):
        return 0 <= x < self.width and 0 <= y < self.height and 0 <= z < self.depth

    def get(self, x, y, z):
        if self.inside(x, y, z):
            return self.blocks[self.index(x, y, z)]
        return AIR

    def set(self, x, y, z, block):
        if self.inside(x, y, z):
            self.blocks[self.index(x, y, z)] = block
            if block != AIR and y >= self.ceiling:
                self.ceiling = y + 1

    def is_solid(self, x, y, z):
        if x < 0 or z < 0 or x >= self.width or z >= self.depth or y < 0:
            return True
        if y >= self.height:
            return False
        return self.blocks[self.index(x, y, z)] != AIR

    def raycast(self, origin, direction, reach):
        pos = [math.floor(origin[0]), math.floor(origin[1]), math.floor(origin[2])]
        step = [0, 0, 0]
        t_delta = [math.inf, math.inf, math.inf]
        t_max = [math.inf, math.inf, math.inf]
        for i in range(3):
            o = origin[i]
            d = direction[i]
            if d > 0:
                step[i] = 1
                t_delta[i] = 1 / d
                t_max[i] = (pos[i] + 1 - o) * t_delta[i]
            elif d < 0:
                step[i] = -1
                t_delta[i] = -1 / d
                t_max[i] = (o - pos[i]) * t_delta[i]
        previous = None
        t = 0.0
        while t <= reach:
            if self.get(pos[0], pos[1], pos[2]) != AIR:
                return (pos[0], pos[1], pos[2]), previous
            previous = (pos[0], pos[1], pos[2])
            axis = 0
            if t_max[1] < t_max[axis]:
                axis = 1
            if t_max[2] < t_max[axis]:
                axis = 2
            t = t_max[axis]
            pos[axis] += step[axis]
            t_max[axis] += t_delta[axis]
        return None, None

    def top(self, x, z):
        for y in range(self.height - 1, -1, -1):
            if self.blocks[self.index(x, y, z)] != AIR:
                return y
        return -1

    def spawn_point(self):
        cx = self.width // 2
        cz = self.depth // 2
        for ground in (GRASS, SAND, STONE):
            for r in range(min(cx, cz) - 2):
                for x in range(cx - r, cx + r + 1):
                    for z in range(cz - r, cz + r + 1):
                        y = self.top(x, z)
                        if self.get(x, y, z) == ground:
                            return x + 0.5, y + 1.0, z + 0.5
        return cx + 0.5, self.height - 4.0, cz + 0.5

    def make_terrain(self, rng):
        w = self.width
        d = self.depth
        wd = w * d
        noise = [0.0] * wd
        for cell, amp in ((128, 1.0), (64, 0.55), (32, 0.3), (16, 0.15), (8, 0.07)):
            layer = value_noise(rng, w, d, cell)
            for i in range(wd):
                noise[i] = noise[i] + layer[i] * amp
        lo = min(noise)
        hi = max(noise)
        scale = 1.0 / (hi - lo)
        self.heights = bytearray(wd)
        columns = {}
        for i in range(wd):
            n = (noise[i] - lo) * scale
            h = min(self.height - 8, 4 + int(n * (0.4 + 0.6 * n) * 52))
            dirt = min(h - 1, 2 + (i * 7919 // 8) % 3)
            if (h, dirt) in columns:
                column = columns[(h, dirt)]
            else:
                if h <= self.SAND_LEVEL:
                    top = bytes([SAND]) * (dirt + 1)
                elif h >= self.ROCK_LEVEL:
                    top = bytes([STONE]) * (dirt + 1)
                else:
                    top = bytes([DIRT]) * dirt + bytes([GRASS])
                column = bytes([BEDROCK]) + bytes([STONE]) * (h - dirt - 1) + top
                columns[(h, dirt)] = column
            # cijeli stupac odjednom, ovako je puno brze nego blok po blok
            self.blocks[i:i + (h + 1) * wd:wd] = column
            self.heights[i] = h
        self.ceiling = max(self.heights) + 1

    def make_ores(self, rng):
        w = self.width
        d = self.depth
        for ore, count, top in ((COAL_ORE, w * d // 60, 40), (GOLD_ORE, w * d // 300, 24),
                                (DIAMOND_ORE, w * d // 900, 12)):
            for i in range(count):
                x = rng.randrange(w)
                z = rng.randrange(d)
                y = rng.randrange(1, top)
                for j in range(rng.randint(1, 4)):
                    if self.get(x, y, z) == STONE:
                        self.set(x, y, z, ore)
                    x += rng.randint(-1, 1)
                    y += rng.randint(-1, 1)
                    z += rng.randint(-1, 1)

    def make_boulders(self, rng):
        for i in range(self.width * self.depth // 900):
            x = rng.randrange(3, self.width - 3)
            z = rng.randrange(3, self.depth - 3)
            y = self.heights[x + z * self.width]
            r = rng.uniform(1.0, 2.2)
            ir = int(r) + 1
            for dx in range(-ir, ir + 1):
                for dy in range(-ir, ir + 1):
                    for dz in range(-ir, ir + 1):
                        if dx * dx + dy * dy + dz * dz <= r * r + rng.random():
                            self.set(x + dx, y + dy, z + dz, STONE)

    def make_trees(self, rng):
        w = self.width
        taken = bytearray(w * self.depth)
        for i in range(w * self.depth // 60):
            x = rng.randrange(3, w - 3)
            z = rng.randrange(3, self.depth - 3)
            y = self.heights[x + z * w]
            if taken[x + z * w] or self.get(x, y, z) != GRASS:
                continue
            for tz in range(z - 3, z + 4):
                for tx in range(x - 3, x + 4):
                    taken[tx + tz * w] = 1
            trunk = rng.randint(4, 6)
            crown = y + trunk
            for dy in range(-2, 2):
                if dy < 0:
                    r = 2
                else:
                    r = 1
                for dx in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        corner = abs(dx) == r and abs(dz) == r
                        if corner and (dy == 1 or rng.random() < 0.5):
                            continue
                        if self.get(x + dx, crown + dy, z + dz) == AIR:
                            self.set(x + dx, crown + dy, z + dz, LEAVES)
            for dy in range(1, trunk + 1):
                self.set(x, y + dy, z, LOG)

    # otoci u zraku, na vrhu je blago
    def make_islands(self, rng):
        w = self.width
        d = self.depth
        for i in range(w * d // 5000):
            r = rng.randint(3, 6)
            cx = rng.randrange(r + 4, w - r - 4)
            cz = rng.randrange(r + 4, d - r - 4)
            ground = 0
            for x in range(cx - r, cx + r + 1):
                for z in range(cz - r, cz + r + 1):
                    if self.heights[x + z * w] > ground:
                        ground = self.heights[x + z * w]
            top = ground + rng.randint(11, 17)
            if top + 3 >= self.height:
                continue
            for dx in range(-r, r + 1):
                for dz in range(-r, r + 1):
                    dist = math.sqrt(dx * dx + dz * dz)
                    if dist > r + rng.random() * 0.8:
                        continue
                    thickness = 1 + int((r - dist) * 0.9) + rng.randint(0, 1)
                    for k in range(thickness):
                        if k == 0:
                            block = GRASS
                        elif k < 3:
                            block = DIRT
                        else:
                            block = STONE
                        self.set(cx + dx, top - k, cz + dz, block)
            self.set(cx, top + 1, cz, SKY_LUCKY)
            self.treasures.append((cx, top + 1, cz))
            for j in range(rng.randint(2, 4)):
                gx = cx + rng.randint(-2, 2)
                gz = cz + rng.randint(-2, 2)
                if self.get(gx, top + 1, gz) == AIR and self.get(gx, top, gz) == GRASS:
                    if rng.random() < 0.25:
                        self.set(gx, top + 1, gz, DIAMOND_BLOCK)
                    else:
                        self.set(gx, top + 1, gz, GOLD_BLOCK)
