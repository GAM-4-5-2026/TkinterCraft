import math
import queue
import random
import time

from objects import AIR, BEDROCK, BLOCKS, HOTBAR, LUCKY, TNT, COBBLESTONE, GOLD_BLOCK
from objects import DIAMOND_BLOCK, LEAVES, LOG, SKY_LUCKY, LUCKY_BLOCKS
from world import World

ROUND_TIME = 300.0
RESULTS_TIME = 12.0
LUCKY_PER_PLAYER = 10
LUCKY_RADIUS = 45
MAX_LUCKY = 200
SKY_CHANCE = 0.3
TNT_FUSE = 3.0
TNT_RADIUS = 3.3

OUTCOMES = [
    ("points", 30), ("jackpot", 3), ("gold", 9), ("diamonds", 6), ("rain", 7), ("tnt", 9),
    ("cage", 6), ("launch", 8), ("speed", 7), ("jump", 7), ("teleport", 4), ("unlucky", 6),
]
SKY_OUTCOMES = ["points", "jackpot", "gold", "diamonds", "rain", "speed", "jump"]


def by_score(item):
    return -item[2]


class Game:

    def __init__(self, world, emit):
        self.world = world
        self.emit = emit
        self.players = {}
        self.owner = None
        self.lucky = set(world.treasures)
        self.tnt = {}
        self.phase = "play"
        self.time_left = ROUND_TIME
        self.spawn_timer = 0.0
        self.round_timer = 0.0
        self.rng = random.Random()

    def add_player(self, pid, name):
        if self.owner is None:
            self.owner = pid
        self.players[pid] = {"name": name, "state": None, "score": 0}

    def welcome(self, pid):
        players = []
        for other in self.players:
            if other != pid:
                p = self.players[other]
                players.append({"id": other, "name": p["name"], "state": p["state"]})
        lucky = []
        for pos in self.lucky:
            lucky.append(list(pos))
        return {"id": pid, "players": players, "lucky": lucky,
                "round": self.round_message(), "scores": self.score_list()}

    def announce(self, pid):
        self.emit({"t": "join", "id": pid, "name": self.players[pid]["name"]}, None, pid)
        self.emit_scores()

    def remove_player(self, pid):
        if pid in self.players:
            del self.players[pid]
            self.emit({"t": "leave", "id": pid})
            self.emit_scores()

    def score_list(self):
        scores = []
        for pid in self.players:
            p = self.players[pid]
            scores.append([pid, p["name"], p["score"]])
        scores.sort(key=by_score)
        return scores

    def emit_scores(self):
        self.emit({"t": "scores", "list": self.score_list()})

    def round_message(self):
        message = {"t": "round", "phase": self.phase, "left": round(self.time_left, 1)}
        if self.phase == "results":
            message["scores"] = self.score_list()
        return message

    def add_points(self, pid, points, text):
        if pid not in self.players or self.phase != "play":
            return
        player = self.players[pid]
        player["score"] = max(0, player["score"] + points)
        self.emit({"t": "event", "text": text, "good": points >= 0}, pid)
        self.emit_scores()

    def handle(self, pid, message):
        kind = message.get("t")
        if kind == "pos":
            state = []
            for v in message["s"]:
                state.append(float(v))
            if len(state) != 5:
                return
            for v in state:
                if not math.isfinite(v):
                    return
            self.players[pid]["state"] = state
            self.emit({"t": "pos", "id": pid, "s": state}, None, pid)
        elif kind == "set":
            self.set_block(pid, int(message["x"]), int(message["y"]), int(message["z"]), int(message["b"]))
        elif kind == "regen" and pid == self.owner:
            self.new_world(World())

    def set_block(self, pid, x, y, z, block):
        world = self.world
        if not world.inside(x, y, z):
            return
        old = world.get(x, y, z)
        allowed = False
        if block == AIR and old != AIR and old != BEDROCK:
            allowed = True
        if block in HOTBAR and old == AIR:
            allowed = True
        if not allowed:
            self.emit({"t": "sets", "list": [[x, y, z, old]]}, pid)
            return
        changes = []
        self.put(x, y, z, block, changes)
        if block == AIR:
            if old in LUCKY_BLOCKS:
                self.open_lucky(pid, x, y, z, changes, old == SKY_LUCKY)
            elif old == TNT:
                if (x, y, z) in self.tnt:
                    del self.tnt[(x, y, z)]
                self.add_points(pid, 15, "TNT deaktiviran! +15")
            elif BLOCKS[old].points:
                points = BLOCKS[old].points
                self.add_points(pid, points, f"+{points} {BLOCKS[old].name}")
        self.emit({"t": "sets", "list": changes})

    def put(self, x, y, z, block, changes):
        if not self.world.inside(x, y, z) or self.world.get(x, y, z) == BEDROCK:
            return
        self.world.set(x, y, z, block)
        changes.append([x, y, z, block])
        if block in LUCKY_BLOCKS:
            self.lucky.add((x, y, z))
        else:
            self.lucky.discard((x, y, z))

    # sta se dogodi kad razbijes lucky blok
    def open_lucky(self, pid, x, y, z, changes, sky):
        rng = self.rng
        names = []
        weights = []
        for name, weight in OUTCOMES:
            if not sky or name in SKY_OUTCOMES:
                names.append(name)
                weights.append(weight)
        outcome = rng.choices(names, weights=weights)[0]
        state = None
        if pid in self.players:
            state = self.players[pid]["state"]
        if sky:
            bonus = 2
        else:
            bonus = 1

        if outcome == "points":
            points = rng.choice([10, 15, 20, 25, 30, 40, 50]) * bonus
            if sky:
                self.add_points(pid, points, f"NEBESKI LUCKY! +{points}")
            else:
                self.add_points(pid, points, f"LUCKY! +{points}")
        elif outcome == "jackpot":
            self.add_points(pid, 100 * bonus, f"*** JACKPOT! +{100 * bonus} ***")
        elif outcome == "gold":
            for dy in range(4):
                if self.world.get(x, y + dy, z) == AIR:
                    self.put(x, y + dy, z, GOLD_BLOCK, changes)
            self.event(pid, "Zlatni toranj! Iskopaj ga (+5 po bloku)")
        elif outcome == "diamonds":
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if self.world.get(x + dx, y, z + dz) == AIR:
                    self.put(x + dx, y, z + dz, DIAMOND_BLOCK, changes)
            self.event(pid, "Dijamanti! Iskopaj ih (+15 po bloku)")
        elif outcome == "rain":
            for i in range(5):
                self.spawn_lucky(x, z, 2, 7, changes, False)
            self.event(pid, "Kisa lucky blokova!")
        elif outcome == "tnt":
            self.put(x, y, z, TNT, changes)
            self.tnt[(x, y, z)] = TNT_FUSE
            self.event(pid, "TNT! BJEZI! (ili ga brzo razbij)", False)
        elif outcome == "cage" and state:
            px = math.floor(state[0])
            py = math.floor(state[1])
            pz = math.floor(state[2])
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for dy in (-1, 0, 1, 2):
                        if dx == 0 and dz == 0 and (dy == 0 or dy == 1):
                            continue
                        if self.world.get(px + dx, py + dy, pz + dz) == AIR:
                            self.put(px + dx, py + dy, pz + dz, COBBLESTONE, changes)
            self.event(pid, "Zarobljen si! Iskopaj se van", False)
        elif outcome == "launch":
            self.event(pid, "RAKETA!", True, "launch")
        elif outcome == "speed":
            self.event(pid, "Brzina! (20 s)", True, "speed")
        elif outcome == "jump":
            self.event(pid, "Super skok! (20 s)", True, "jump")
        elif outcome == "teleport":
            tx = rng.randrange(8, self.world.width - 8)
            tz = rng.randrange(8, self.world.depth - 8)
            ty = self.world.top(tx, tz) + 1
            self.event(pid, "Teleport!", True, "teleport", [tx + 0.5, ty, tz + 0.5])
        else:
            self.add_points(pid, -25, "Unlucky... -25")

    def event(self, pid, text, good=True, effect=None, pos=None):
        message = {"t": "event", "text": text, "good": good}
        if effect is not None:
            message["effect"] = effect
        if pos is not None:
            message["pos"] = pos
        self.emit(message, pid)

    def spawn_lucky(self, cx, cz, near, far, changes, sky):
        world = self.world
        angle = self.rng.uniform(0, 2 * math.pi)
        dist = self.rng.uniform(near, far)
        x = int(cx + math.sin(angle) * dist)
        z = int(cz + math.cos(angle) * dist)
        if x < 2 or x >= world.width - 2 or z < 2 or z >= world.depth - 2:
            return
        ground = world.top(x, z)
        if world.get(x, ground, z) in (LUCKY, SKY_LUCKY, TNT, LEAVES, LOG):
            return
        if sky:
            y = ground + self.rng.randint(9, 13)
            if y < world.height - 1:
                self.put(x, y, z, SKY_LUCKY, changes)
        elif 0 < ground + 1 < world.height - 1:
            self.put(x, ground + 1, z, LUCKY, changes)

    def update(self, dt):
        changes = []
        self.round_timer -= dt
        self.time_left -= dt
        if self.time_left <= 0:
            if self.phase == "play":
                self.phase = "results"
                self.time_left = RESULTS_TIME
            else:
                self.phase = "play"
                self.time_left = ROUND_TIME
                for pid in self.players:
                    self.players[pid]["score"] = 0
                self.emit_scores()
            self.round_timer = 0
        if self.round_timer <= 0:
            self.round_timer = 1.0
            self.emit(self.round_message())

        for pos in list(self.tnt):
            self.tnt[pos] -= dt
            if self.tnt[pos] <= 0:
                self.explode(pos, changes)

        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_timer = 1.0
            for pid in self.players:
                state = self.players[pid]["state"]
                if not state or len(self.lucky) >= MAX_LUCKY:
                    continue
                near = 0
                for pos in self.lucky:
                    if abs(pos[0] - state[0]) < LUCKY_RADIUS and abs(pos[2] - state[2]) < LUCKY_RADIUS:
                        near += 1
                for i in range(min(3, LUCKY_PER_PLAYER - near)):
                    sky = self.rng.random() < SKY_CHANCE
                    self.spawn_lucky(state[0], state[2], 6, LUCKY_RADIUS, changes, sky)
        if changes:
            self.emit({"t": "sets", "list": changes})

    def explode(self, pos, changes):
        if pos in self.tnt:
            del self.tnt[pos]
        x = pos[0]
        y = pos[1]
        z = pos[2]
        r = int(TNT_RADIUS) + 1
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for dz in range(-r, r + 1):
                    if dx * dx + dy * dy + dz * dz > TNT_RADIUS * TNT_RADIUS:
                        continue
                    p = (x + dx, y + dy, z + dz)
                    block = self.world.get(p[0], p[1], p[2])
                    if block == AIR or block == BEDROCK:
                        continue
                    if block == TNT and p in self.tnt:
                        self.tnt[p] = min(self.tnt[p], 0.3)
                        continue
                    self.put(p[0], p[1], p[2], AIR, changes)
        self.emit({"t": "boom", "x": x + 0.5, "y": y + 0.5, "z": z + 0.5})
        for pid in self.players:
            s = self.players[pid]["state"]
            if s and (s[0] - x - 0.5) ** 2 + (s[1] + 0.9 - y - 0.5) ** 2 + (s[2] - z - 0.5) ** 2 < 25:
                self.add_points(pid, -15, "Pogodio te TNT! -15")

    def new_world(self, world):
        self.world = world
        self.lucky = set(world.treasures)
        self.tnt.clear()
        lucky = []
        for pos in self.lucky:
            lucky.append(list(pos))
        self.emit({"t": "world", "world": world, "lucky": lucky})


class LocalLink:

    def __init__(self, name, world=None):
        if world is None:
            world = World()
        self.inbox = queue.Queue()
        self.game = Game(world, self.emit)
        self.game.add_player(1, name)
        self.id = 1
        self.address = ""
        self.connected = True
        self.welcome = self.game.welcome(1)
        self.world = self.game.world
        self.last_update = time.perf_counter()

    def emit(self, message, to=None, skip=None):
        if skip == self.id:
            return
        if to is None or to == self.id:
            self.inbox.put(message)

    def send(self, message):
        self.game.handle(self.id, message)

    def poll(self):
        now = time.perf_counter()
        self.game.update(now - self.last_update)
        self.last_update = now
        messages = []
        while not self.inbox.empty():
            messages.append(self.inbox.get())
        return messages

    def close(self):
        pass
