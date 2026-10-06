import math
import random

from objects import BLOCKS

# od tamnog prema svijetlom: mracno je tockica, svijetlo je #
SHADES = ".:;-=+*%#"
LEVELS = len(SHADES)
# Tk Text je brz samo s malo boja, pa svaki materijal ima samo BANDS nijansi,
# a finu svjetlinu odreduje znak
BANDS = 3
LEVEL_BAND = [level * BANDS // LEVELS for level in range(LEVELS)]

# svjetlina strana bloka (sunce dolazi odozgo, malo s +x i +z strane)
LIGHT_TOP = 1.0
LIGHT_BOTTOM = 0.45
LIGHT_X = (0.9, 0.68)
LIGHT_Z = (0.8, 0.58)

SKY = [
    ("-", (175, 205, 240)),
    ("-", (140, 185, 245)),
    ("~", (100, 155, 235)),
    (".", (70, 120, 220)),
]
# daleki blokovi se stapaju s nebom (magla)
FOG = [(0.6, (125, 145, 170)), (0.82, (155, 180, 210))]
SUN = ("@", (255, 240, 150))
CLOUD = ("#", (245, 245, 250))
CROSSHAIR = ("+", (255, 255, 255))
OUTLINE = ("#", (255, 255, 255))
# drugi igraci: koza, hlace, majice (boja ovisi o igracu) i ime iznad glave
SKIN = (225, 175, 135)
PANTS = (60, 60, 175)
SHIRTS = [(0, 185, 185), (210, 60, 60), (235, 205, 40), (120, 205, 60), (180, 95, 210), (245, 145, 40)]
NAME = (255, 255, 255)
SUN_DIR = (0.45, 0.62, 0.64)
CLOUD_HEIGHT = 60.0
CLOUD_SCALE = 6.0


def hex_color(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


class Renderer:

    def __init__(self, world, view_distance=56.0, fov=70.0):
        self.world = world
        self.view_distance = view_distance
        self.fov = math.radians(fov)
        self.cols = self.rows = 0
        self.col_u = []
        self.row_v = []
        self._build_tags()
        rng = random.Random(1234)
        self.noise = [rng.uniform(-1.0, 1.0) for _ in range(256)]
        self.clouds = self._make_clouds(rng)

    def _build_tags(self):
        # svaki tag je jedna boja u Text widgetu
        self.tag_colors = []
        materials = {}
        self.texture = []
        self.faces = [None] * len(BLOCKS)
        for block_id, block in enumerate(BLOCKS):
            if block is None:
                continue
            ids = []
            for rgb in (block.side, block.top, block.bottom):
                key = (rgb, block.texture)
                if key not in materials:
                    materials[key] = len(materials)
                    self.texture.append(block.texture)
                    for band in range(BANDS):
                        k = 0.55 + 0.45 * band / (BANDS - 1)
                        self.tag_colors.append(hex_color([c * k for c in rgb]))
                ids.append(materials[key])
            ids.append(ids[1] if block.strip else -1)
            self.faces[block_id] = tuple(ids)
        self.fog_tag = len(self.tag_colors)
        for _, rgb in FOG:
            self.tag_colors.append(hex_color(rgb))
        self.sky_tag = len(self.tag_colors)
        self.sun_tag = self.sky_tag + len(SKY)
        self.cloud_tag = self.sun_tag + 1
        self.cross_tag = self.cloud_tag + 1
        self.outline_tag = self.cross_tag + 1
        self.sky_chars = [char for char, _ in SKY]
        for _, rgb in SKY + [SUN, CLOUD, CROSSHAIR, OUTLINE]:
            self.tag_colors.append(hex_color(rgb))
        self.skin_tag = len(self.tag_colors)
        self.pants_tag = self.skin_tag + 1
        self.name_tag = self.skin_tag + 2
        self.shirt_tag = self.skin_tag + 3
        for rgb in [SKIN, PANTS, NAME] + SHIRTS:
            self.tag_colors.append(hex_color(rgb))
        self.tag_names = ["t%d" % i for i in range(len(self.tag_colors))]

    def _make_clouds(self, rng):
        size = 32
        cells = [rng.random() for _ in range(size * size)]
        clouds = bytearray(size * size)
        for z in range(size):
            for x in range(size):
                s = sum(cells[(x + dx) % size + ((z + dz) % size) * size]
                        for dx in (-1, 0, 1) for dz in (-1, 0, 1))
                clouds[x + z * size] = s > 5.6
        return clouds

    def resize(self, cols, rows, aspect):
        # aspect = sirina / visina ekrana u pikselima
        self.cols, self.rows = cols, rows
        tan_v = math.tan(self.fov / 2)
        tan_h = tan_v * aspect
        self.tan_h, self.tan_v = tan_h, tan_v
        self.col_u = [(2 * (i + 0.5) / cols - 1) * tan_h for i in range(cols)]
        self.row_v = [(1 - 2 * (j + 0.5) / rows) * tan_v for j in range(rows)]

    def render(self, px, py, pz, yaw, pitch, target=-1, players=()):
        """Vraca argumente za Text.insert: (znakovi, tag, znakovi, tag, ...)."""
        world = self.world
        W, D, H = world.width, world.depth, world.height
        WD = W * D
        blocks = world.blocks
        faces = self.faces
        texture = self.texture
        noise = self.noise
        clouds = self.clouds
        tag_names = self.tag_names
        maxd = self.view_distance
        inv_maxd = 1.0 / maxd
        fog_near, fog_far = FOG[0][0] * maxd, FOG[1][0] * maxd
        fog_tag = self.fog_tag
        top_level = LEVELS - 1
        level_band = LEVEL_BAND
        shades = SHADES
        sky_tag = self.sky_tag
        sky_chars = self.sky_chars
        sky_bands = len(SKY)
        sun_tag, cloud_tag = self.sun_tag, self.cloud_tag
        sun_char, cloud_char = SUN[0], CLOUD[0]
        outline_tag, outline_char = self.outline_tag, OUTLINE[0]
        sun_x, sun_y, sun_z = SUN_DIR
        inf = float("inf")

        sin_y, cos_y = math.sin(yaw), math.cos(yaw)
        sin_p, cos_p = math.sin(pitch), math.cos(pitch)
        fx, fy, fz = cos_p * sin_y, sin_p, cos_p * cos_y
        rx, rz = cos_y, -sin_y
        ux, uy, uz = -sin_p * sin_y, cos_p, -sin_p * cos_y

        ix0, iy0, iz0 = math.floor(px), math.floor(py), math.floor(pz)
        idx0 = ix0 + iz0 * W + iy0 * WD
        cross_row, cross_col = self.rows // 2, self.cols // 2

        screen = []
        for v in self.row_v:
            bx = fx + v * ux
            dy = fy + v * uy
            bz = fz + v * uz
            if dy > 0:
                sty, styi, tdy = 1, WD, 1.0 / dy
                tmy0 = (iy0 + 1 - py) * tdy
            elif dy < 0:
                sty, styi, tdy = -1, -WD, -1.0 / dy
                tmy0 = (py - iy0) * tdy
            else:
                sty, styi, tdy, tmy0 = 0, 0, inf, inf

            row_chars = []
            row_tags = []
            row_depth = []
            for u in self.col_u:
                dx = bx + u * rx
                dz = bz + u * rz
                if dx > 0:
                    stx, tdx = 1, 1.0 / dx
                    tmx = (ix0 + 1 - px) * tdx
                elif dx < 0:
                    stx, tdx = -1, -1.0 / dx
                    tmx = (px - ix0) * tdx
                else:
                    stx, tdx, tmx = 0, inf, inf
                if dz > 0:
                    stz, stzi, tdz = 1, W, 1.0 / dz
                    tmz = (iz0 + 1 - pz) * tdz
                elif dz < 0:
                    stz, stzi, tdz = -1, -W, -1.0 / dz
                    tmz = (pz - iz0) * tdz
                else:
                    stz, stzi, tdz, tmz = 0, 0, inf, inf

                x, y, z, idx, tmy = ix0, iy0, iz0, idx0, tmy0
                tag = -1
                depth = inf
                # DDA: korak po korak kroz mrezu blokova dok zraka ne udari blok
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
                        if y < 0 or y >= H:
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
                    if not block:
                        continue

                    depth = t
                    side, top, bottom, strip = faces[block]
                    if face == 1:
                        if sty < 0:
                            mat, light = top, LIGHT_TOP
                        else:
                            mat, light = bottom, LIGHT_BOTTOM
                        a = px + dx * t - x
                        c = pz + dz * t - z
                    else:
                        c = py + dy * t - y
                        if face == 0:
                            a = pz + dz * t - z
                            light = LIGHT_X[stx > 0]
                        else:
                            a = px + dx * t - x
                            light = LIGHT_Z[stz > 0]
                        mat = strip if strip >= 0 and c > 0.8 else side

                    light *= 1.0 + texture[mat] * noise[(int(a * 4) + int(c * 4) * 4 + idx * 37) & 255]
                    if t < 12.0 and (a < 0.06 or a > 0.94 or c < 0.06 or c > 0.94):
                        # rub bloka na koji igrac cilja
                        if idx == target:
                            tag, char = outline_tag, outline_char
                            break
                        light *= 0.65
                    light *= 1.0 - 0.3 * t * inv_maxd
                    level = int(light * top_level + 0.5)
                    if level > top_level:
                        level = top_level
                    elif level < 0:
                        level = 0
                    char = shades[level]
                    if t < fog_near:
                        tag = mat * BANDS + level_band[level]
                    elif t < fog_far:
                        tag = fog_tag
                    else:
                        tag = fog_tag + 1
                    break

                if tag < 0:
                    inv = 1.0 / math.sqrt(dx * dx + dy * dy + dz * dz)
                    band = 0
                    if (dx * sun_x + dy * sun_y + dz * sun_z) * inv > 0.995:
                        tag, char = sun_tag, sun_char
                    else:
                        if dy > 0:
                            band = int(dy * inv * sky_bands * 1.4)
                            if band >= sky_bands:
                                band = sky_bands - 1
                            tc = (CLOUD_HEIGHT - py) / dy
                            if tc < 400.0:
                                cx = int((px + dx * tc) / CLOUD_SCALE + 10000) & 31
                                cz = int((pz + dz * tc) / CLOUD_SCALE + 10000) & 31
                                if clouds[cx + cz * 32]:
                                    tag, char = cloud_tag, cloud_char
                        if tag < 0:
                            tag, char = sky_tag + band, sky_chars[band]
                row_chars.append(char)
                row_tags.append(tag)
                row_depth.append(depth)
            screen.append((row_chars, row_tags, row_depth))

        basis = ((fx, fy, fz), (rx, 0.0, rz), (ux, uy, uz))
        for player in players:
            self._draw_player(screen, (px, py, pz), basis, *player)
        row_chars, row_tags, _ = screen[cross_row]
        row_chars[cross_col] = CROSSHAIR[0]
        row_tags[cross_col] = self.cross_tag

        out = []
        for row_chars, row_tags, _ in screen:
            # spoji susjedne znakove iste boje u jedan komad teksta
            row_chars.append("\n")
            prev, start = row_tags[0], 0
            for i, tag in enumerate(row_tags):
                if tag != prev:
                    out.append("".join(row_chars[start:i]))
                    out.append(tag_names[prev])
                    prev, start = tag, i
            out.append("".join(row_chars[start:]))
            out.append(tag_names[prev])
        return out

    def _project(self, eye, basis, point):
        """Tocka u svijetu -> (stupac, redak, dubina) na ekranu."""
        (fx, fy, fz), (rx, _, rz), (ux, uy, uz) = basis
        dx, dy, dz = point[0] - eye[0], point[1] - eye[1], point[2] - eye[2]
        z = dx * fx + dy * fy + dz * fz
        if z < 0.2:
            return None
        x = dx * rx + dz * rz
        y = dx * ux + dy * uy + dz * uz
        col = (x / z / self.tan_h + 1) * self.cols / 2 - 0.5
        row = (1 - y / z / self.tan_v) * self.rows / 2 - 0.5
        return col, row, z

    def _draw_player(self, screen, eye, basis, x, y, z, name, color):
        # lik je ploha okrenuta prema kameri: noge, tijelo, glava
        parts = (
            (0.0, 0.72, 0.3, "#", self.pants_tag),
            (0.72, 1.38, 0.3, "#", self.shirt_tag + color % len(SHIRTS)),
            (1.38, 1.85, 0.25, "@", self.skin_tag),
        )
        head_row = None
        for bottom, top, half, char, tag in parts:
            low = self._project(eye, basis, (x, y + bottom, z))
            high = self._project(eye, basis, (x, y + top, z))
            if low is None or high is None:
                return
            depth = (low[2] + high[2]) / 2
            if depth > self.view_distance:
                return
            col = (low[0] + high[0]) / 2
            width = half / depth / self.tan_h * self.cols / 2
            # celije ciji je centar unutar dijela tijela (barem jedna)
            r0, r1 = math.ceil(high[1]), math.floor(low[1])
            if r0 > r1:
                r0 = r1 = round((high[1] + low[1]) / 2)
            c0, c1 = math.ceil(col - width), math.floor(col + width)
            if c0 > c1:
                c0 = c1 = round(col)
            for r in range(max(0, r0), min(self.rows - 1, r1) + 1):
                row_chars, row_tags, row_depth = screen[r]
                for c in range(max(0, c0), min(self.cols - 1, c1) + 1):
                    if depth < row_depth[c]:
                        row_chars[c] = char
                        row_tags[c] = tag
                        row_depth[c] = depth
            head_row, head_col = r0 - 1, col
        if head_row is not None and 0 <= head_row < self.rows:
            label = name[:16]
            start = round(head_col - len(label) / 2)
            row_chars, row_tags, _ = screen[head_row]
            for i, ch in enumerate(label):
                if 0 <= start + i < self.cols:
                    row_chars[start + i] = ch
                    row_tags[start + i] = self.name_tag
