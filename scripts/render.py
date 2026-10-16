import math
import random

from objects import BLOCKS

SHADES = ".:;-=+*%#"
LEVELS = len(SHADES)
BANDS = 3
LEVEL_BAND = []
for level in range(LEVELS):
    LEVEL_BAND.append(level * BANDS // LEVELS)

LIGHT_TOP = 1.0
LIGHT_BOTTOM = 0.45
LIGHT_X1 = 0.9
LIGHT_X2 = 0.68
LIGHT_Z1 = 0.8
LIGHT_Z2 = 0.58

SKY = [
    ("-", (175, 205, 240)),
    ("-", (140, 185, 245)),
    ("~", (100, 155, 235)),
    (".", (70, 120, 220)),
]
FOG = [(0.6, (125, 145, 170)), (0.82, (155, 180, 210))]
SUN = ("@", (255, 240, 150))
CLOUD = ("#", (245, 245, 250))
CROSSHAIR = ("+", (255, 255, 255))
OUTLINE = ("#", (255, 255, 255))
SKIN = (225, 175, 135)
PANTS = (60, 60, 175)
SHIRTS = [(0, 185, 185), (210, 60, 60), (235, 205, 40), (120, 205, 60), (180, 95, 210), (245, 145, 40)]
NAME = (255, 255, 255)
SUN_DIR = (0.45, 0.62, 0.64)
CLOUD_HEIGHT = 60.0
CLOUD_SCALE = 6.0


def clamp_color(c):
    c = int(c)
    if c < 0:
        c = 0
    if c > 255:
        c = 255
    return c


def hex_color(rgb):
    r = clamp_color(rgb[0])
    g = clamp_color(rgb[1])
    b = clamp_color(rgb[2])
    return "#%02x%02x%02x" % (r, g, b)


class Renderer:

    def __init__(self, world, view_distance=56.0, fov=70.0):
        self.world = world
        self.view_distance = view_distance
        self.fov = math.radians(fov)
        self.cols = 0
        self.rows = 0
        self.col_u = []
        self.row_v = []
        self.build_tags()
        rng = random.Random(1234)
        self.noise = []
        for i in range(256):
            self.noise.append(rng.uniform(-1.0, 1.0))
        self.clouds = self.make_clouds(rng)

    def add_material(self, materials, rgb, texture):
        key = (rgb, texture)
        if key not in materials:
            materials[key] = len(materials)
            self.texture.append(texture)
            for band in range(BANDS):
                k = 0.55 + 0.45 * band / (BANDS - 1)
                self.tag_colors.append(hex_color((rgb[0] * k, rgb[1] * k, rgb[2] * k)))
        return materials[key]

    def build_tags(self):
        self.tag_colors = []
        self.texture = []
        materials = {}
        self.faces = [None] * len(BLOCKS)
        for block_id in range(len(BLOCKS)):
            block = BLOCKS[block_id]
            if block is None:
                continue
            side = self.add_material(materials, block.side, block.texture)
            top = self.add_material(materials, block.top, block.texture)
            bottom = self.add_material(materials, block.bottom, block.texture)
            speck = -1
            if block.speck is not None:
                speck = self.add_material(materials, block.speck, block.texture)
            strip = -1
            if block.strip:
                strip = top
            self.faces[block_id] = (side, top, bottom, strip, speck, block.char, block.glow)

        self.fog_tag = len(self.tag_colors)
        for fog in FOG:
            self.tag_colors.append(hex_color(fog[1]))
        self.sky_tag = len(self.tag_colors)
        self.sun_tag = self.sky_tag + len(SKY)
        self.cloud_tag = self.sun_tag + 1
        self.cross_tag = self.cloud_tag + 1
        self.outline_tag = self.cross_tag + 1
        self.sky_chars = []
        for sky in SKY:
            self.sky_chars.append(sky[0])
            self.tag_colors.append(hex_color(sky[1]))
        for thing in (SUN, CLOUD, CROSSHAIR, OUTLINE):
            self.tag_colors.append(hex_color(thing[1]))
        self.skin_tag = len(self.tag_colors)
        self.pants_tag = self.skin_tag + 1
        self.name_tag = self.skin_tag + 2
        self.shirt_tag = self.skin_tag + 3
        self.tag_colors.append(hex_color(SKIN))
        self.tag_colors.append(hex_color(PANTS))
        self.tag_colors.append(hex_color(NAME))
        for shirt in SHIRTS:
            self.tag_colors.append(hex_color(shirt))
        self.tag_names = []
        for i in range(len(self.tag_colors)):
            self.tag_names.append("t" + str(i))

    def make_clouds(self, rng):
        size = 32
        cells = []
        for i in range(size * size):
            cells.append(rng.random())
        clouds = bytearray(size * size)
        for z in range(size):
            for x in range(size):
                s = 0
                for dx in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        s = s + cells[(x + dx) % size + ((z + dz) % size) * size]
                if s > 5.6:
                    clouds[x + z * size] = 1
        return clouds

    def resize(self, cols, rows, aspect):
        self.cols = cols
        self.rows = rows
        self.tan_v = math.tan(self.fov / 2)
        self.tan_h = self.tan_v * aspect
        self.col_u = []
        for i in range(cols):
            self.col_u.append((2 * (i + 0.5) / cols - 1) * self.tan_h)
        self.row_v = []
        for j in range(rows):
            self.row_v.append((1 - 2 * (j + 0.5) / rows) * self.tan_v)

    # raycasting: za svaki znak na ekranu ide zraka dok ne udari u blok
    def render(self, px, py, pz, yaw, pitch, target=-1, players=None):
        world = self.world
        W = world.width
        D = world.depth
        H = world.height
        WD = W * D
        blocks = world.blocks
        faces = self.faces
        texture = self.texture
        noise = self.noise
        clouds = self.clouds
        tag_names = self.tag_names
        maxd = self.view_distance
        inv_maxd = 1.0 / maxd
        fog_near = FOG[0][0] * maxd
        fog_far = FOG[1][0] * maxd
        fog_tag = self.fog_tag
        top_level = LEVELS - 1
        sky_bands = len(SKY)
        inf = float("inf")

        sin_y = math.sin(yaw)
        cos_y = math.cos(yaw)
        sin_p = math.sin(pitch)
        cos_p = math.cos(pitch)
        fx = cos_p * sin_y
        fy = sin_p
        fz = cos_p * cos_y
        rx = cos_y
        rz = -sin_y
        ux = -sin_p * sin_y
        uy = cos_p
        uz = -sin_p * cos_y

        ceiling = world.ceiling
        ix0 = math.floor(px)
        iy0 = math.floor(py)
        iz0 = math.floor(pz)
        idx0 = ix0 + iz0 * W + iy0 * WD

        screen = []
        for v in self.row_v:
            bx = fx + v * ux
            dy = fy + v * uy
            bz = fz + v * uz
            if dy > 0:
                sty = 1
                styi = WD
                tdy = 1.0 / dy
                tmy0 = (iy0 + 1 - py) * tdy
            elif dy < 0:
                sty = -1
                styi = -WD
                tdy = -1.0 / dy
                tmy0 = (py - iy0) * tdy
            else:
                sty = 0
                styi = 0
                tdy = inf
                tmy0 = inf
            if sty > 0:
                ylimit = ceiling
            else:
                ylimit = H

            row_chars = []
            row_tags = []
            row_depth = []
            for u in self.col_u:
                dx = bx + u * rx
                dz = bz + u * rz
                if dx > 0:
                    stx = 1
                    tdx = 1.0 / dx
                    tmx = (ix0 + 1 - px) * tdx
                elif dx < 0:
                    stx = -1
                    tdx = -1.0 / dx
                    tmx = (px - ix0) * tdx
                else:
                    stx = 0
                    tdx = inf
                    tmx = inf
                if dz > 0:
                    stz = 1
                    stzi = W
                    tdz = 1.0 / dz
                    tmz = (iz0 + 1 - pz) * tdz
                elif dz < 0:
                    stz = -1
                    stzi = -W
                    tdz = -1.0 / dz
                    tmz = (pz - iz0) * tdz
                else:
                    stz = 0
                    stzi = 0
                    tdz = inf
                    tmz = inf

                x = ix0
                y = iy0
                z = iz0
                idx = idx0
                tmy = tmy0
                tag = -1
                depth = inf
                while True:
                    if tmx < tmy and tmx < tmz:
                        t = tmx
                        if t > maxd:
                            break
                        x += stx
                        if x < 0 or x >= W:
                            break
                        idx += stx
                        tmx += tdx
                        face = 0
                    elif tmy < tmz:
                        t = tmy
                        if t > maxd:
                            break
                        y += sty
                        if y < 0 or y >= ylimit:
                            break
                        idx += styi
                        tmy += tdy
                        face = 1
                    else:
                        t = tmz
                        if t > maxd:
                            break
                        z += stz
                        if z < 0 or z >= D:
                            break
                        idx += stzi
                        tmz += tdz
                        face = 2
                    block = blocks[idx]
                    if block == 0:
                        continue

                    depth = t
                    info = faces[block]
                    strip = info[3]
                    speck = info[4]
                    glow = info[6]
                    if face == 1:
                        if sty < 0:
                            mat = info[1]
                            light = LIGHT_TOP
                        else:
                            mat = info[2]
                            light = LIGHT_BOTTOM
                        a = px + dx * t - x
                        c = pz + dz * t - z
                    else:
                        c = py + dy * t - y
                        if face == 0:
                            a = pz + dz * t - z
                            if stx > 0:
                                light = LIGHT_X2
                            else:
                                light = LIGHT_X1
                        else:
                            a = px + dx * t - x
                            if stz > 0:
                                light = LIGHT_Z2
                            else:
                                light = LIGHT_Z1
                        if strip >= 0 and c > 0.8:
                            mat = strip
                        else:
                            mat = info[0]

                    grain = noise[(int(a * 4) + int(c * 4) * 4 + idx * 37) % 256]
                    if speck >= 0 and grain > 0.45:
                        mat = speck
                    light *= 1.0 + texture[mat] * grain
                    if t < 12.0 and (a < 0.06 or a > 0.94 or c < 0.06 or c > 0.94):
                        if idx == target:
                            tag = self.outline_tag
                            char = OUTLINE[0]
                            break
                        light *= 0.65
                    if not glow:
                        light *= 1.0 - 0.3 * t * inv_maxd
                    level = int(light * top_level + 0.5)
                    if level > top_level:
                        level = top_level
                    elif level < 0:
                        level = 0
                    if info[5]:
                        char = info[5]
                    else:
                        char = SHADES[level]
                    if t < fog_near or glow:
                        tag = mat * BANDS + LEVEL_BAND[level]
                    elif t < fog_far:
                        tag = fog_tag
                    else:
                        tag = fog_tag + 1
                    break

                if tag < 0:
                    inv = 1.0 / math.sqrt(dx * dx + dy * dy + dz * dz)
                    band = 0
                    if (dx * SUN_DIR[0] + dy * SUN_DIR[1] + dz * SUN_DIR[2]) * inv > 0.995:
                        tag = self.sun_tag
                        char = SUN[0]
                    else:
                        if dy > 0:
                            band = int(dy * inv * sky_bands * 1.4)
                            if band >= sky_bands:
                                band = sky_bands - 1
                            tc = (CLOUD_HEIGHT - py) / dy
                            if tc < 400.0:
                                cx = int((px + dx * tc) / CLOUD_SCALE + 10000) % 32
                                cz = int((pz + dz * tc) / CLOUD_SCALE + 10000) % 32
                                if clouds[cx + cz * 32]:
                                    tag = self.cloud_tag
                                    char = CLOUD[0]
                        if tag < 0:
                            tag = self.sky_tag + band
                            char = self.sky_chars[band]
                row_chars.append(char)
                row_tags.append(tag)
                row_depth.append(depth)
            screen.append([row_chars, row_tags, row_depth])

        if players:
            self.eye = (px, py, pz)
            self.forward = (fx, fy, fz)
            self.right = (rx, 0.0, rz)
            self.up = (ux, uy, uz)
            for p in players:
                self.draw_player(screen, p[0], p[1], p[2], p[3], p[4])

        middle = screen[self.rows // 2]
        middle[0][self.cols // 2] = CROSSHAIR[0]
        middle[1][self.cols // 2] = self.cross_tag

        # znakovi iste boje idu zajedno, inace je tkinter jako spor
        out = []
        for line in screen:
            row_chars = line[0]
            row_tags = line[1]
            row_chars.append("\n")
            prev = row_tags[0]
            start = 0
            for i in range(len(row_tags)):
                if row_tags[i] != prev:
                    out.append("".join(row_chars[start:i]))
                    out.append(tag_names[prev])
                    prev = row_tags[i]
                    start = i
            out.append("".join(row_chars[start:]))
            out.append(tag_names[prev])
        return out

    def project(self, x, y, z):
        dx = x - self.eye[0]
        dy = y - self.eye[1]
        dz = z - self.eye[2]
        f = self.forward
        depth = dx * f[0] + dy * f[1] + dz * f[2]
        if depth < 0.2:
            return None
        sx = dx * self.right[0] + dz * self.right[2]
        sy = dx * self.up[0] + dy * self.up[1] + dz * self.up[2]
        col = (sx / depth / self.tan_h + 1) * self.cols / 2 - 0.5
        row = (1 - sy / depth / self.tan_v) * self.rows / 2 - 0.5
        return col, row, depth

    def draw_player(self, screen, x, y, z, name, color):
        parts = [
            (0.0, 0.72, 0.3, "#", self.pants_tag),
            (0.72, 1.38, 0.3, "#", self.shirt_tag + color % len(SHIRTS)),
            (1.38, 1.85, 0.25, "@", self.skin_tag),
        ]
        head_row = None
        head_col = 0
        for part in parts:
            bottom = part[0]
            top = part[1]
            half = part[2]
            char = part[3]
            tag = part[4]
            low = self.project(x, y + bottom, z)
            high = self.project(x, y + top, z)
            if low is None or high is None:
                return
            depth = (low[2] + high[2]) / 2
            if depth > self.view_distance:
                return
            col = (low[0] + high[0]) / 2
            width = half / depth / self.tan_h * self.cols / 2
            r0 = math.ceil(high[1])
            r1 = math.floor(low[1])
            if r0 > r1:
                r0 = round((high[1] + low[1]) / 2)
                r1 = r0
            c0 = math.ceil(col - width)
            c1 = math.floor(col + width)
            if c0 > c1:
                c0 = round(col)
                c1 = c0
            for r in range(max(0, r0), min(self.rows - 1, r1) + 1):
                line = screen[r]
                for c in range(max(0, c0), min(self.cols - 1, c1) + 1):
                    if depth < line[2][c]:
                        line[0][c] = char
                        line[1][c] = tag
                        line[2][c] = depth
            head_row = r0 - 1
            head_col = col
        if head_row is not None and 0 <= head_row < self.rows:
            label = name[:16]
            start = round(head_col - len(label) / 2)
            line = screen[head_row]
            for i in range(len(label)):
                if 0 <= start + i < self.cols:
                    line[0][start + i] = label[i]
                    line[1][start + i] = self.name_tag
