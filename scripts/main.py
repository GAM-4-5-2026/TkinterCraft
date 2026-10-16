import json
import math
import os
import random
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

import net
from game import LocalLink
from objects import AIR, BEDROCK, BLOCKS, HOTBAR, LUCKY_BLOCKS, Player
from render import Renderer
from world import World, world_from_message

TITLE = "TkinterCraft"
ROWS = 50
MIN_ROWS = 24
MAX_ROWS = 120
VIEW_DISTANCES = [16, 24, 32, 48, 64, 96, 128]
FONT_FAMILY = "Courier"
LOOK_SPEED = 2.2
MOUSE_SENSITIVITY = 0.004
REACH = 5.0
RECORD_FILE = os.path.join(os.path.expanduser("~"), ".tkintercraft.json")
ARROWS = "↑↗→↘↓↙←↖"
HELP = ("WASD hodanje | Shift trcanje | Space skok | strelice/mis gledanje | klik = zakljucaj mis, Esc = otkljucaj\n"
        "lijevi klik/Q razbij | desni klik/E postavi | 1-9/kotacic blok | +/- render distance | "
        "PgUp/PgDn rezolucija | R novi svijet")


def load_record():
    try:
        with open(RECORD_FILE) as f:
            data = json.load(f)
        return int(data.get("record", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def save_record(record):
    try:
        with open(RECORD_FILE, "w") as f:
            json.dump({"record": record}, f)
    except OSError:
        pass


class TkinterCraft:

    def __init__(self, root, client, server=None, name="Igrac"):
        self.root = root
        self.client = client
        self.server = server
        self.name = name
        self.solo = isinstance(client, LocalLink)
        self.others = {}
        self.lucky = set()
        self.message = ""
        self.sent_state = None
        self.sent_time = 0.0
        self.host_ip = None
        if server:
            self.host_ip = net.local_ip()
        self.view_index = VIEW_DISTANCES.index(64)
        self.record = load_record()
        self.scores = []
        self.phase = "play"
        self.time_left = 0.0
        self.banner_until = 0.0

        self.help = tk.Label(root, text=HELP, font=(FONT_FAMILY, 9), bg="black", fg="gray60",
                             anchor="w", justify="left")
        self.help.pack(side="bottom", fill="x")
        self.status = tk.Label(root, font=(FONT_FAMILY, 10), bg="black", fg="lightgreen", anchor="w")
        self.status.pack(side="bottom", fill="x")
        self.screen = tk.Frame(root, bg="black")
        self.screen.pack(fill="both", expand=True)

        self.font = tkfont.Font(family=FONT_FAMILY, size=-8)
        self.probe = tkfont.Font(family=FONT_FAMILY, size=-8)
        self.text_area = tk.Text(self.screen, font=self.font, bg="black", fg="white", wrap="none",
                                 bd=0, highlightthickness=0, padx=0, pady=0, insertwidth=0,
                                 cursor="crosshair")
        self.text_area.place(relx=0.5, rely=0.5, anchor="center")
        self.text_area.bindtags((str(self.text_area), str(root), "all"))

        self.hud = tk.Label(self.screen, font=(FONT_FAMILY, 13, "bold"), fg="#ffd700", bg="black",
                            padx=8, pady=2)
        self.hud.place(x=8, y=6, anchor="nw")
        self.board = tk.Label(self.screen, font=(FONT_FAMILY, 11, "bold"), fg="white", bg="black",
                              padx=8, pady=2, justify="left")
        self.board.place(relx=1.0, x=-8, y=6, anchor="ne")
        self.banner = tk.Label(self.screen, font=(FONT_FAMILY, 20, "bold"), fg="#ffd700", bg="black",
                               padx=8, pady=2)
        self.hotbar = tk.Label(self.screen, font=(FONT_FAMILY, 11, "bold"), fg="white", bg="black",
                               padx=8, pady=2)
        self.hotbar.place(relx=0.5, rely=1.0, y=-6, anchor="s")
        self.hud_texts = {}

        self.rows = ROWS
        self.cols = 0
        self.keys = set()
        self.pending_release = {}
        self.mouse_locked = False
        self.selected = 0
        self.target = None
        self.place_at = None

        self.set_world(client.world)
        self.load_welcome(client.welcome)

        root.bind("<KeyPress>", self.on_key_down)
        root.bind("<KeyRelease>", self.on_key_up)
        root.bind("<FocusOut>", self.on_focus_out)
        for widget in (self.text_area, self.hud, self.board, self.banner, self.hotbar):
            widget.bind("<Button-1>", self.on_left_click)
            widget.bind("<Button-2>", self.on_right_click)
            widget.bind("<Button-3>", self.on_right_click)
            widget.bind("<MouseWheel>", self.on_wheel)
            widget.bind("<Button-4>", self.on_wheel_up)
            widget.bind("<Button-5>", self.on_wheel_down)
        self.screen.bind("<Configure>", self.on_resize)

        self.last_time = time.perf_counter()
        self.last_camera = None
        self.frames = 0
        self.frame_time = 0.0
        self.fps = 0.0
        self.fps_time = self.last_time
        self.text_area.focus_set()
        self.select_block(0)
        self.show_banner("Razbijaj lucky blokove (?) za bodove!", "#ffd700", 4)
        self.tick()

    def load_welcome(self, welcome):
        self.others = {}
        for p in welcome["players"]:
            self.others[p["id"]] = {"name": p["name"], "state": p["state"]}
        self.lucky = set()
        for pos in welcome["lucky"]:
            self.lucky.add((pos[0], pos[1], pos[2]))
        self.scores = welcome["scores"]
        self.apply_round(welcome["round"])

    def new_world(self):
        if self.solo or self.server:
            self.client.send({"t": "regen"})
        else:
            self.message = "samo host moze napraviti novi svijet"

    def set_world(self, world):
        self.world = world
        self.lucky = set()
        self.player = Player(world.spawn_point())
        self.player.yaw = 0.6
        self.renderer = Renderer(self.world, VIEW_DISTANCES[self.view_index])
        for i in range(len(self.renderer.tag_names)):
            self.text_area.tag_configure(self.renderer.tag_names[i], foreground=self.renderer.tag_colors[i])
        self.fit_screen()

    def on_resize(self, event):
        self.fit_screen()

    def fit_screen(self):
        width = self.screen.winfo_width()
        height = self.screen.winfo_height()
        if width < 10 or height < 10:
            return
        size = 4
        for px in range(4, 64):
            self.probe.configure(size=-px)
            if self.probe.metrics("linespace") * self.rows > height:
                break
            size = px
        self.probe.configure(size=-size)
        char_w = max(1, self.probe.measure("#"))
        char_h = self.probe.metrics("linespace")
        self.cols = max(8, width // char_w)
        self.font.configure(size=-size)
        self.text_area.configure(width=self.cols, height=self.rows)
        self.renderer.resize(self.cols, self.rows, (self.cols * char_w) / (self.rows * char_h))
        self.last_camera = None

    def on_key_down(self, event):
        key = event.keysym.lower()
        # kad drzis tipku linux salje pusti/stisni pa ovo to ignorira
        if key in self.pending_release:
            self.root.after_cancel(self.pending_release[key])
            del self.pending_release[key]
        if key not in self.keys:
            self.keys.add(key)
            self.on_key_pressed(key)

    def on_key_up(self, event):
        key = event.keysym.lower()
        if key in self.pending_release:
            self.root.after_cancel(self.pending_release[key])
        self.pending_release[key] = self.root.after(30, self.release_key, key)

    def release_key(self, key):
        if key in self.pending_release:
            del self.pending_release[key]
        self.keys.discard(key)

    def on_key_pressed(self, key):
        if key == "escape":
            self.unlock_mouse()
        elif key == "r":
            self.new_world()
        elif key == "q":
            self.break_block()
        elif key == "e":
            self.place_block()
        elif key.isdigit() and key != "0":
            self.select_block(int(key) - 1)
        elif key == "plus" or key == "kp_add" or key == "equal":
            self.set_view(self.view_index + 1)
        elif key == "minus" or key == "kp_subtract":
            self.set_view(self.view_index - 1)
        elif key == "prior":
            self.rows = min(MAX_ROWS, self.rows + 8)
            self.fit_screen()
        elif key == "next":
            self.rows = max(MIN_ROWS, self.rows - 8)
            self.fit_screen()

    def set_view(self, index):
        self.view_index = max(0, min(len(VIEW_DISTANCES) - 1, index))
        self.renderer.view_distance = VIEW_DISTANCES[self.view_index]
        self.message = f"render distance {self.renderer.view_distance}"
        self.last_camera = None
        self.update_status()

    def on_left_click(self, event):
        if self.mouse_locked:
            self.break_block()
        else:
            self.lock_mouse()

    def on_right_click(self, event):
        self.place_block()

    def on_wheel(self, event):
        if event.delta > 0:
            self.select_block(self.selected - 1)
        else:
            self.select_block(self.selected + 1)

    def on_wheel_up(self, event):
        self.select_block(self.selected - 1)

    def on_wheel_down(self, event):
        self.select_block(self.selected + 1)

    def select_block(self, slot):
        self.selected = slot % len(HOTBAR)
        parts = []
        for i in range(len(HOTBAR)):
            label = f"{i + 1} {BLOCKS[HOTBAR[i]].name}"
            if i == self.selected:
                parts.append("[" + label + "]")
            else:
                parts.append(" " + label + " ")
        self.set_hud(self.hotbar, " ".join(parts))

    def set_hud(self, label, text):
        if self.hud_texts.get(label) != text:
            self.hud_texts[label] = text
            label.configure(text=text)

    def show_banner(self, text, color="#ffd700", seconds=2.5):
        self.banner.configure(text=text, fg=color)
        self.banner.place(relx=0.5, rely=0.28, anchor="center")
        self.banner_until = time.perf_counter() + seconds

    def update_target(self):
        p = self.player
        eye = (p.x, p.y + p.EYE_HEIGHT, p.z)
        result = self.world.raycast(eye, p.look_direction(), REACH)
        self.target = result[0]
        self.place_at = result[1]

    def break_block(self):
        self.update_target()
        if self.target is None:
            return
        x, y, z = self.target
        if self.world.get(x, y, z) != BEDROCK:
            self.change_block(x, y, z, AIR)

    def place_block(self):
        self.update_target()
        if self.place_at is None:
            return
        bx, by, bz = self.place_at
        if not self.world.inside(bx, by, bz):
            return
        p = self.player
        if p.overlaps(bx, by, bz):
            # blok pod nogama, igrac se digne gore (za gradit toranj)
            if by != math.floor(p.y + 1e-3) or not p.fits(self.world, by + 1):
                return
            p.y = by + 1.0
            p.vy = max(p.vy, 0.0)
        for pid in self.others:
            s = self.others[pid]["state"]
            if s and bx < s[0] + 0.3 and bx + 1 > s[0] - 0.3 and by < s[1] + 1.8 and by + 1 > s[1] \
                    and bz < s[2] + 0.3 and bz + 1 > s[2] - 0.3:
                return
        self.change_block(bx, by, bz, HOTBAR[self.selected])

    def change_block(self, x, y, z, block):
        self.client.send({"t": "set", "x": x, "y": y, "z": z, "b": block})
        self.world.set(x, y, z, block)
        if block not in LUCKY_BLOCKS:
            self.lucky.discard((x, y, z))
        self.last_camera = None

    def network(self, now):
        client = self.client
        try:
            for msg in client.poll():
                self.handle(msg)
                if self.client is not client:
                    return
        except (KeyError, TypeError, ValueError, IndexError):
            pass
        if not self.client.connected:
            self.disconnect("veza sa serverom je prekinuta")
            return
        p = self.player
        state = [round(p.x, 2), round(p.y, 2), round(p.z, 2), round(p.yaw, 2), round(p.pitch, 2)]
        if state != self.sent_state and now - self.sent_time > 0.05:
            self.client.send({"t": "pos", "s": state})
            self.sent_state = state
            self.sent_time = now

    def handle(self, msg):
        kind = msg.get("t")
        if kind == "pos":
            if msg["id"] not in self.others:
                self.others[msg["id"]] = {"name": "?", "state": None}
            self.others[msg["id"]]["state"] = msg["s"]
        elif kind == "join":
            self.others[msg["id"]] = {"name": msg["name"], "state": None}
            self.message = f"{msg['name']} je usao u igru"
        elif kind == "leave":
            if msg["id"] in self.others:
                self.message = f"{self.others[msg['id']]['name']} je izasao iz igre"
                del self.others[msg["id"]]
            self.last_camera = None
        elif kind == "sets":
            for change in msg["list"]:
                x, y, z, block = change
                self.world.set(x, y, z, block)
                if block in LUCKY_BLOCKS:
                    self.lucky.add((x, y, z))
                else:
                    self.lucky.discard((x, y, z))
            self.last_camera = None
        elif kind == "world":
            if isinstance(msg["world"], World):
                self.set_world(msg["world"])
            else:
                self.set_world(world_from_message(msg["world"]))
            for pos in msg.get("lucky", []):
                self.lucky.add((pos[0], pos[1], pos[2]))
            self.show_banner("Novi svijet!")
        elif kind == "event":
            if msg.get("good", True):
                self.show_banner(msg["text"], "#ffd700")
            else:
                self.show_banner(msg["text"], "#ff5050")
            self.apply_effect(msg)
        elif kind == "scores":
            self.scores = msg["list"]
        elif kind == "round":
            self.apply_round(msg)
        elif kind == "boom":
            self.boom(msg["x"], msg["y"], msg["z"])
        elif kind == "disconnect":
            self.disconnect("veza sa serverom je prekinuta")

    def apply_effect(self, msg):
        effect = msg.get("effect")
        p = self.player
        if effect == "launch":
            p.vy = 24.0
            p.on_ground = False
        elif effect == "speed" or effect == "jump":
            p.effects[effect] = 20.0
        elif effect == "teleport":
            p.x = msg["pos"][0]
            p.y = msg["pos"][1]
            p.z = msg["pos"][2]
            p.vx = 0.0
            p.vy = 0.0
            p.vz = 0.0

    def boom(self, x, y, z):
        p = self.player
        dx = p.x - x
        dy = p.y + 0.9 - y
        dz = p.z - z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 7:
            push = (7 - dist) * 2.5 / max(dist, 0.5)
            p.vx += dx * push
            p.vz += dz * push
            p.vy = max(p.vy, 6 + (7 - dist) * 1.5)
            p.on_ground = False
            self.root.bell()
        self.last_camera = None

    def apply_round(self, msg):
        phase = msg["phase"]
        if phase == "results" and self.phase == "play":
            self.round_over(msg.get("scores", self.scores))
        elif phase == "play" and self.phase == "results":
            self.show_banner("NOVA RUNDA! Skupi sto vise bodova", "#80ff80", 3)
        self.phase = phase
        self.time_left = msg["left"]

    def round_over(self, scores):
        mine = self.my_score()
        text = "KRAJ RUNDE!"
        if len(scores) > 1:
            text += f"  Pobjednik: {scores[0][1]} ({scores[0][2]})"
        if mine > self.record:
            self.record = mine
            save_record(mine)
            text += f"  NOVI REKORD: {mine}!"
        else:
            text += f"  Tvoji bodovi: {mine}"
        self.show_banner(text, "#80ff80", 10)

    def my_score(self):
        for score in self.scores:
            if score[0] == self.client.id:
                return score[2]
        return 0

    def disconnect(self, reason):
        if not self.solo:
            self.client.close()
        lucky = self.lucky
        self.client = LocalLink(self.name, self.world)
        self.solo = True
        for pos in lucky:
            self.client.game.lucky.add(pos)
        self.load_welcome(self.client.welcome)
        self.lucky = set(lucky)
        self.server = None
        self.message = reason + " - igras sam"
        self.last_camera = None

    def close(self):
        self.client.close()
        if self.server:
            self.server.close()
        self.root.destroy()

    def nearest_lucky(self):
        p = self.player
        best = None
        best_dist = 0
        for pos in self.lucky:
            dist = (pos[0] + 0.5 - p.x) ** 2 + (pos[2] + 0.5 - p.z) ** 2
            if best is None or dist < best_dist:
                best = pos
                best_dist = dist
        return best

    def update_hud(self):
        p = self.player
        seconds = max(0, int(self.time_left))
        minutes = seconds // 60
        seconds = seconds % 60
        if self.phase == "play":
            text = f"Vrijeme {minutes}:{seconds:02d}   Bodovi {self.my_score()}"
        else:
            text = f"Nova runda za {seconds} s"
        lucky = self.nearest_lucky()
        if lucky is not None:
            dx = lucky[0] + 0.5 - p.x
            dz = lucky[2] + 0.5 - p.z
            angle = math.atan2(dx, dz) - p.yaw
            arrow = ARROWS[round(angle / (math.pi / 4)) % 8]
            text += f"   ? {int(math.hypot(dx, dz))} m {arrow}"
            if lucky[1] - p.y > 3:
                text += f" ({int(lucky[1] - p.y)} gore)"
        if "speed" in p.effects:
            text += f"   BRZINA {int(p.effects['speed'])}s"
        if "jump" in p.effects:
            text += f"   SKOK {int(p.effects['jump'])}s"
        self.set_hud(self.hud, text)

        if self.solo:
            board = f"Rekord: {self.record}"
        else:
            lines = []
            for i in range(min(8, len(self.scores))):
                name = self.scores[i][1][:12]
                lines.append(f"{i + 1}. {name:<12} {self.scores[i][2]:4d}")
            board = "\n".join(lines)
        self.set_hud(self.board, board)

    def update_status(self):
        p = self.player
        if self.server:
            mode = f"host {self.host_ip}:{self.server.port}, igraca {len(self.others) + 1}"
        elif not self.solo:
            mode = f"spojen na {self.client.address}, igraca {len(self.others) + 1}"
        else:
            mode = "singleplayer"
        text = (f"{TITLE}  FPS {self.fps:4.1f}  XYZ {p.x:5.1f} {p.y:5.1f} {p.z:5.1f}  "
                f"{self.cols}x{self.rows}  render {self.renderer.view_distance}  |  {mode}")
        if self.message:
            text += "  |  " + self.message
        self.status.configure(text=text)

    def on_focus_out(self, event):
        self.keys.clear()
        self.unlock_mouse()

    def lock_mouse(self):
        self.text_area.focus_set()
        self.mouse_locked = True
        try:
            self.text_area.configure(cursor="none")
        except tk.TclError:
            pass
        self.warp_mouse()

    def unlock_mouse(self):
        if self.mouse_locked:
            self.mouse_locked = False
            self.text_area.configure(cursor="crosshair")

    # mis se svaki put vrati u sredinu ekrana
    def warp_mouse(self):
        x = self.text_area.winfo_width() // 2
        y = self.text_area.winfo_height() // 2
        self.text_area.event_generate("<Motion>", warp=True, x=x, y=y)
        self.text_area.update_idletasks()

    def mouse_look(self):
        x = self.text_area.winfo_width() // 2
        y = self.text_area.winfo_height() // 2
        mx = self.root.winfo_pointerx() - self.text_area.winfo_rootx()
        my = self.root.winfo_pointery() - self.text_area.winfo_rooty()
        dx = mx - x
        dy = my - y
        if dx != 0 or dy != 0:
            self.player.look(dx * MOUSE_SENSITIVITY, -dy * MOUSE_SENSITIVITY)
            self.warp_mouse()

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self.last_time, 0.25)
        self.last_time = now

        turn = 0
        if "right" in self.keys:
            turn += 1
        if "left" in self.keys:
            turn -= 1
        tilt = 0
        if "up" in self.keys:
            tilt += 1
        if "down" in self.keys:
            tilt -= 1
        if turn != 0 or tilt != 0:
            self.player.look(turn * LOOK_SPEED * dt, tilt * LOOK_SPEED * dt)
        if self.mouse_locked:
            self.mouse_look()
        self.player.update(dt, self.keys, self.world)
        self.network(now)
        self.time_left -= dt

        self.update_target()
        target = -1
        if self.target is not None:
            target = self.world.index(self.target[0], self.target[1], self.target[2])
        players = []
        for pid in self.others:
            s = self.others[pid]["state"]
            if s:
                players.append((s[0], s[1], s[2], self.others[pid]["name"], pid))
        p = self.player
        camera = (p.x, p.y + p.EYE_HEIGHT, p.z, p.yaw, p.pitch, target, players)
        # crta se samo ako se nesto promijenilo
        if camera != self.last_camera and self.cols:
            self.last_camera = camera
            chunks = self.renderer.render(p.x, p.y + p.EYE_HEIGHT, p.z, p.yaw, p.pitch, target, players)
            self.draw(chunks)
            self.frames += 1
            self.frame_time += time.perf_counter() - now

        self.update_hud()
        if self.banner_until and now > self.banner_until:
            self.banner_until = 0.0
            self.banner.place_forget()
        if now - self.fps_time >= 0.5:
            if self.frames:
                self.fps = self.frames / max(self.frame_time, 1e-6)
            self.frames = 0
            self.frame_time = 0.0
            self.fps_time = now
            self.update_status()

        spent = (time.perf_counter() - now) * 1000
        self.root.after(max(1, int(1000 / 60 - spent)), self.tick)

    def draw(self, chunks):
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", *chunks)
        self.text_area.update_idletasks()


def parse_address(text):
    text = text.strip()
    if ":" in text:
        host = text[:text.rindex(":")]
        port = text[text.rindex(":") + 1:]
        if host and port.isdigit():
            return host, int(port)
    return text, net.PORT


class StartMenu:

    def __init__(self, root, name, on_start):
        self.root = root
        self.on_start = on_start
        self.servers = []
        self.searching = False
        font = (FONT_FAMILY, 12)

        self.frame = tk.Frame(root, bg="black")
        self.frame.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(self.frame, text=TITLE, bg="black", fg="lightgreen",
                 font=(FONT_FAMILY, 40, "bold")).pack(pady=(0, 18))

        row = tk.Frame(self.frame, bg="black")
        row.pack(pady=4)
        tk.Label(row, text="Ime:", bg="black", fg="lightgreen", font=font).pack(side="left")
        self.name = tk.Entry(row, width=20, bg="#1e1e1e", fg="lightgreen", font=font, insertbackground="white")
        self.name.insert(0, name)
        self.name.pack(side="left", padx=6)

        self.make_button("Igraj sam", self.solo).pack(pady=(12, 4))
        self.make_button("Napravi igru na mrezi (host)", self.host).pack(pady=4)

        tk.Label(self.frame, text="Igre na lokalnoj mrezi:", bg="black", fg="lightgreen",
                 font=font).pack(pady=(16, 2))
        self.list = tk.Listbox(self.frame, height=5, width=46, bg="#1e1e1e", fg="lightgreen", font=font,
                               selectbackground="#2e6b2e", highlightthickness=0)
        self.list.pack()
        self.list.bind("<Double-Button-1>", self.on_double_click)
        self.make_button("Osvjezi popis", self.refresh).pack(pady=(6, 2))
        self.make_button("Spoji se na odabranu igru", self.join_selected).pack(pady=2)

        row = tk.Frame(self.frame, bg="black")
        row.pack(pady=(14, 4))
        tk.Label(row, text="IP adresa:", bg="black", fg="lightgreen", font=font).pack(side="left")
        self.address = tk.Entry(row, width=22, bg="#1e1e1e", fg="lightgreen", font=font, insertbackground="white")
        self.address.pack(side="left", padx=6)
        self.address.bind("<Return>", self.on_enter)
        self.make_button("Spoji se na IP adresu", self.join_address).pack(pady=2)

        self.info = tk.Label(self.frame, text="", bg="black", fg="orange", font=(FONT_FAMILY, 11))
        self.info.pack(pady=(12, 0))
        self.refresh()

    def make_button(self, text, command):
        return tk.Button(self.frame, text=text, command=command, bg="#1e1e1e", fg="lightgreen",
                         font=(FONT_FAMILY, 12), activebackground="#333333", activeforeground="white", width=34)

    def on_double_click(self, event):
        self.join_selected()

    def on_enter(self, event):
        self.join_address()

    def player_name(self):
        name = self.name.get().strip()[:16]
        if name == "":
            name = "Igrac"
        return name

    def say(self, text):
        self.info.configure(text=text)
        self.root.update_idletasks()

    def refresh(self):
        if self.searching:
            return
        self.searching = True
        self.say("trazim igre na mrezi...")
        result = []
        thread = threading.Thread(target=self.search, args=(result,), daemon=True)
        thread.start()
        self.root.after(100, self.wait_for_search, thread, result)

    def search(self, result):
        servers = net.discover()
        for server in servers:
            result.append(server)

    def wait_for_search(self, thread, result):
        if thread.is_alive():
            self.root.after(100, self.wait_for_search, thread, result)
            return
        self.searching = False
        if not self.frame.winfo_exists():
            return
        self.servers = result
        self.list.delete(0, tk.END)
        for server in result:
            self.list.insert(tk.END, f"{server[2]}  ({server[0]}:{server[1]}, igraca {server[3]})")
        self.say(f"pronadeno igara: {len(result)}")

    def solo(self):
        self.say("generiram svijet...")
        self.start(LocalLink(self.player_name()), None)

    def host(self):
        self.say("generiram svijet i pokrecem server...")
        try:
            server = net.Server(self.player_name())
        except OSError as e:
            self.say(f"ne mogu pokrenuti server: {e}")
            return
        try:
            client = net.Client("127.0.0.1", server.port, self.player_name())
        except (OSError, ValueError) as e:
            server.close()
            self.say(f"ne mogu se spojiti na svoj server: {e}")
            return
        self.start(client, server)

    def join(self, host, port):
        self.say(f"spajam se na {host}:{port}...")
        try:
            client = net.Client(host, port, self.player_name())
        except (OSError, ValueError) as e:
            self.say(f"ne mogu se spojiti: {e}")
            return
        self.start(client, None)

    def join_selected(self):
        selection = self.list.curselection()
        if not selection:
            self.say("odaberi igru s popisa")
            return
        server = self.servers[selection[0]]
        self.join(server[0], server[1])

    def join_address(self):
        if self.address.get().strip() == "":
            self.say("upisi IP adresu hosta")
            return
        host, port = parse_address(self.address.get())
        self.join(host, port)

    def start(self, client, server):
        name = self.player_name()
        self.frame.destroy()
        self.on_start(client, server, name)


root = None


def start_game(client, server, name):
    app = TkinterCraft(root, client, server, name)
    root.protocol("WM_DELETE_WINDOW", app.close)


def main():
    global root
    name = "Igrac" + str(random.randint(100, 999))
    solo = False
    host = False
    join = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--name" and i + 1 < len(args):
            name = args[i + 1]
            i += 1
        elif args[i] == "--solo":
            solo = True
        elif args[i] == "--host":
            host = True
        elif args[i] == "--join" and i + 1 < len(args):
            join = args[i + 1]
            i += 1
        i += 1

    root = tk.Tk()
    root.title(TITLE)
    root.geometry("1200x700")
    root.configure(bg="black")
    if solo:
        start_game(LocalLink(name), None, name)
    elif host:
        server = net.Server(name)
        start_game(net.Client("127.0.0.1", server.port, name), server, name)
    elif join:
        address = parse_address(join)
        start_game(net.Client(address[0], address[1], name), None, name)
    else:
        StartMenu(root, name, start_game)
    root.mainloop()


if __name__ == "__main__":
    main()
