import math
import random

from objects import AIR, GRASS, DIRT, STONE, SAND, LOG, LEAVES, BEDROCK


def value_noise(rng, width, depth, cell):
    gw = width // cell + 2
    gd = depth // cell + 2
    grid = [rng.random() for _ in range(gw * gd)]
    out = [0.0] * (width * depth)
    for z in range(depth):
        gz, fz = divmod(z, cell)
        tz = fz / cell
        tz = tz * tz * (3 - 2 * tz)
        for x in range(width):
            gx, fx = divmod(x, cell)
            tx = fx / cell
            tx = tx * tx * (3 - 2 * tx)
            i = gx + gz * gw
            a, b = grid[i], grid[i + 1]
            c, d = grid[i + gw], grid[i + gw + 1]
            near = a + (b - a) * tx
            far = c + (d - c) * tx
            out[x + z * width] = near + (far - near) * tz
    return out


class World:
    SAND_LEVEL = 10
    ROCK_LEVEL = 25

    def __init__(self, width=96, depth=96, height=40, seed=None, blocks=None):
        self.width = width
        self.depth = depth
        self.height = height
        self.seed = random.randrange(1 << 30) if seed is None else seed
        if blocks is not None:
            # svijet primljen preko mreze
            self.blocks = bytearray(blocks)
            return
        self.blocks = bytearray(width * depth * height)
        rng = random.Random(self.seed)
        self._terrain(rng)
        self._boulders(rng)
        self._trees(rng)

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

    def is_solid(self, x, y, z):
        # rubovi svijeta su nevidljivi zid, a ispod svijeta je tlo
        if x < 0 or z < 0 or x >= self.width or z >= self.depth or y < 0:
            return True
        if y >= self.height:
            return False
        return self.blocks[self.index(x, y, z)] != AIR

    def raycast(self, origin, direction, reach):
        """Prvi blok na koji gleda igrac i prazno polje ispred njega."""
        ox, oy, oz = origin
        pos = [math.floor(ox), math.floor(oy), math.floor(oz)]
        step, t_delta, t_max = [0, 0, 0], [math.inf] * 3, [math.inf] * 3
        for i, (o, d) in enumerate(zip(origin, direction)):
            if d > 0:
                step[i], t_delta[i] = 1, 1 / d
                t_max[i] = (pos[i] + 1 - o) * t_delta[i]
            elif d < 0:
                step[i], t_delta[i] = -1, -1 / d
                t_max[i] = (o - pos[i]) * t_delta[i]
        previous = None
        t = 0.0
        while t <= reach:
            if self.get(*pos) != AIR:
                return tuple(pos), previous
            previous = tuple(pos)
            axis = t_max.index(min(t_max))
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
        cx, cz = self.width // 2, self.depth // 2
        for ground in (GRASS, SAND, STONE):
            for r in range(min(cx, cz) - 2):
                for x in range(cx - r, cx + r + 1):
                    for z in range(cz - r, cz + r + 1):
                        y = self.top(x, z)
                        if self.get(x, y, z) == ground:
                            return x + 0.5, y + 1.0, z + 0.5
        return cx + 0.5, self.height - 4.0, cz + 0.5

    def _terrain(self, rng):
        w, d = self.width, self.depth
        noise = [0.0] * (w * d)
        for cell, amp in ((32, 1.0), (16, 0.5), (8, 0.25), (4, 0.12)):
            layer = value_noise(rng, w, d, cell)
            for i in range(w * d):
                noise[i] += layer[i] * amp
        lo, hi = min(noise), max(noise)
        for z in range(d):
            for x in range(w):
                n = (noise[x + z * w] - lo) / (hi - lo)
                h = 5 + int(n ** 1.4 * 24)
                dirt = rng.randint(2, 4)
                for y in range(h + 1):
                    if y == 0:
                        block = BEDROCK
                    elif y < h - dirt:
                        block = STONE
                    elif h <= self.SAND_LEVEL:
                        block = SAND
                    elif h >= self.ROCK_LEVEL:
                        block = STONE
                    elif y < h:
                        block = DIRT
                    else:
                        block = GRASS
                    self.blocks[self.index(x, y, z)] = block

    def _boulders(self, rng):
        for _ in range(self.width * self.depth // 900):
            x = rng.randrange(3, self.width - 3)
            z = rng.randrange(3, self.depth - 3)
            y = self.top(x, z)
            r = rng.uniform(1.0, 2.2)
            ir = int(r) + 1
            for dx in range(-ir, ir + 1):
                for dy in range(-ir, ir + 1):
                    for dz in range(-ir, ir + 1):
                        if dx * dx + dy * dy + dz * dz <= r * r + rng.random():
                            self.set(x + dx, y + dy, z + dz, STONE)

    def _trees(self, rng):
        trees = []
        for _ in range(self.width * self.depth // 60):
            x = rng.randrange(3, self.width - 3)
            z = rng.randrange(3, self.depth - 3)
            y = self.top(x, z)
            if self.get(x, y, z) != GRASS:
                continue
            if any(abs(x - tx) < 4 and abs(z - tz) < 4 for tx, tz in trees):
                continue
            trees.append((x, z))
            trunk = rng.randint(4, 6)
            crown = y + trunk
            for dy in range(-2, 2):
                r = 2 if dy < 0 else 1
                for dx in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        corner = abs(dx) == r and abs(dz) == r
                        if corner and (dy == 1 or rng.random() < 0.5):
                            continue
                        if self.get(x + dx, crown + dy, z + dz) == AIR:
                            self.set(x + dx, crown + dy, z + dz, LEAVES)
            for dy in range(1, trunk + 1):
                self.set(x, y + dy, z, LOG)
