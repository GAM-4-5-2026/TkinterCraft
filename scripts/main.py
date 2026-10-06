import argparse
import random
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

import net
from objects import AIR, BEDROCK, BLOCKS, HOTBAR, Player
from render import Renderer
from world import World

TITLE = "TkinterCraft"
ROWS = 50
MIN_ROWS, MAX_ROWS = 24, 120
FONT_FAMILY = "Courier"
LOOK_SPEED = 2.2          # radijana u sekundi (strelice)
MOUSE_SENSITIVITY = 0.004  # radijana po pikselu
REACH = 5.0               # koliko daleko igrac dohvaca blokove
HELP = ("WASD hodanje | Shift trcanje | Space skok | strelice/mis gledanje | klik = zakljucaj mis, Esc = otkljucaj\n"
        "lijevi klik/Q razbij | desni klik/E postavi | 1-9/kotacic odabir bloka | +/- rezolucija | R novi svijet")


class TkinterCraft:

    def __init__(self, root, client=None, server=None):
        self.root = root
        self.client = client
        self.server = server
        self.others = {}
        self.message = ""
        self.sent_state = None
        self.sent_time = 0.0
        self.host_ip = net.local_ip() if server else None

        self.help = tk.Label(root, text=HELP, font=(FONT_FAMILY, 9), bg="black", fg="gray60", anchor="w", justify="left")
        self.help.pack(side="bottom", fill="x")
        self.status = tk.Label(root, font=(FONT_FAMILY, 10), bg="black", fg="lightgreen", anchor="w")
        self.status.pack(side="bottom", fill="x")
        self.screen = tk.Frame(root, bg="black")
        self.screen.pack(fill="both", expand=True)

        self.font = tkfont.Font(family=FONT_FAMILY, size=-8)
        self.probe = tkfont.Font(family=FONT_FAMILY, size=-8)
        self.text_area = tk.Text(
            self.screen,
            font=self.font,
            bg="black",
            fg="white",
            wrap="none",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            insertwidth=0,
            cursor="crosshair",
        )
        self.text_area.place(relx=0.5, rely=0.5, anchor="center")
        # bez ugradenih Text precica (oznacavanje, scroll, tipkanje)
        self.text_area.bindtags((str(self.text_area), str(root), "all"))

        self.rows = ROWS
        self.cols = 0
        self.keys = set()
        self.pending_release = {}
        self.mouse_locked = False
        self.selected = 0
        self.target = self.place_at = None

        if client:
            self.set_world(client.world)
            for p in client.players:
                self.others[p["id"]] = {"name": p["name"], "state": p["state"]}
        else:
            self.set_world(World())

        root.bind("<KeyPress>", self.on_key_down)
        root.bind("<KeyRelease>", self.on_key_up)
        root.bind("<FocusOut>", self.on_focus_out)
        self.text_area.bind("<Button-1>", self.on_left_click)
        # desni klik je Button-3 (na macOS-u Button-2)
        self.text_area.bind("<Button-2>", lambda e: self.place_block())
        self.text_area.bind("<Button-3>", lambda e: self.place_block())
        self.text_area.bind("<MouseWheel>", lambda e: self.select_block(self.selected + (-1 if e.delta > 0 else 1)))
        self.text_area.bind("<Button-4>", lambda e: self.select_block(self.selected - 1))
        self.text_area.bind("<Button-5>", lambda e: self.select_block(self.selected + 1))
        self.screen.bind("<Configure>", lambda e: self.fit_screen())

        self.last_time = time.perf_counter()
        self.last_camera = None
        self.frames = 0
        self.frame_time = 0.0
        self.fps = 0.0
        self.fps_time = self.last_time
        self.text_area.focus_set()
        self.tick()

    def new_world(self):
        if not self.client:
            self.set_world(World())
        elif self.server:
            # novi svijet moze napraviti samo host, server ga salje svima
            self.client.send({"t": "regen"})
        else:
            self.message = "samo host moze napraviti novi svijet"

    def set_world(self, world):
        self.world = world
        self.player = Player(world.spawn_point())
        self.player.yaw = 0.6
        self.renderer = Renderer(self.world)
        for name, color in zip(self.renderer.tag_names, self.renderer.tag_colors):
            self.text_area.tag_configure(name, foreground=color)
        self.fit_screen()

    def fit_screen(self):
        width = self.screen.winfo_width()
        height = self.screen.winfo_height()
        if width < 10 or height < 10:
            return
        # najveci font kod kojeg ROWS redaka stane u prozor
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
        # autorepeat salje release+press parove; ponisti lazni release
        pending = self.pending_release.pop(key, None)
        if pending:
            self.root.after_cancel(pending)
        if key not in self.keys:
            self.keys.add(key)
            self.on_key_pressed(key)

    def on_key_up(self, event):
        key = event.keysym.lower()
        pending = self.pending_release.pop(key, None)
        if pending:
            self.root.after_cancel(pending)
        self.pending_release[key] = self.root.after(30, self.release_key, key)

    def release_key(self, key):
        self.pending_release.pop(key, None)
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
        elif key in ("plus", "kp_add", "equal"):
            self.rows = min(MAX_ROWS, self.rows + 8)
            self.fit_screen()
        elif key in ("minus", "kp_subtract"):
            self.rows = max(MIN_ROWS, self.rows - 8)
            self.fit_screen()

    def on_left_click(self, event):
        if self.mouse_locked:
            self.break_block()
        else:
            self.lock_mouse()

    def select_block(self, slot):
        self.selected = slot % len(HOTBAR)
        self.update_status()

    def update_target(self):
        p = self.player
        eye = p.camera()[:3]
        self.target, self.place_at = self.world.raycast(eye, p.look_direction(), REACH)

    def break_block(self):
        self.update_target()
        if self.target and self.world.get(*self.target) != BEDROCK:
            self.change_block(self.target, AIR)

    def place_block(self):
        self.update_target()
        spot = self.place_at
        if not spot or not self.world.inside(*spot) or self.player.overlaps(*spot):
            return
        bx, by, bz = spot
        for other in self.others.values():
            s = other["state"]
            # ne postavljaj blok u drugog igraca
            if s and bx < s[0] + 0.3 and bx + 1 > s[0] - 0.3 and by < s[1] + 1.8 and by + 1 > s[1] \
                    and bz < s[2] + 0.3 and bz + 1 > s[2] - 0.3:
                return
        self.change_block(spot, HOTBAR[self.selected])

    def change_block(self, pos, block):
        self.world.set(*pos, block)
        self.last_camera = None
        if self.client:
            x, y, z = pos
            self.client.send({"t": "set", "x": x, "y": y, "z": z, "b": block})

    def network(self, now):
        try:
            for msg in self.client.poll():
                kind = msg.get("t")
                if kind == "pos":
                    self.others.setdefault(msg["id"], {"name": "?", "state": None})["state"] = msg["s"]
                elif kind == "join":
                    self.others[msg["id"]] = {"name": msg["name"], "state": None}
                    self.message = "%s je usao u igru" % msg["name"]
                elif kind == "leave":
                    gone = self.others.pop(msg["id"], None)
                    if gone:
                        self.message = "%s je izasao iz igre" % gone["name"]
                    self.last_camera = None
                elif kind == "set":
                    self.world.set(msg["x"], msg["y"], msg["z"], msg["b"])
                    self.last_camera = None
                elif kind == "world":
                    self.set_world(net.decode_world(msg["world"]))
                    self.message = "host je napravio novi svijet"
                elif kind == "disconnect":
                    self.disconnect("veza sa serverom je prekinuta")
                    return
        except (KeyError, TypeError, ValueError):
            pass
        if not self.client.connected:
            self.disconnect("veza sa serverom je prekinuta")
            return
        # svoju poziciju saljemo ~20 puta u sekundi, samo kad se promijeni
        p = self.player
        state = [round(p.x, 2), round(p.y, 2), round(p.z, 2), round(p.yaw, 2), round(p.pitch, 2)]
        if state != self.sent_state and now - self.sent_time > 0.05:
            self.client.send({"t": "pos", "s": state})
            self.sent_state, self.sent_time = state, now

    def disconnect(self, reason):
        if self.client:
            self.client.close()
        self.client = None
        self.others.clear()
        self.message = reason + " - igras sam"
        self.last_camera = None

    def close(self):
        if self.client:
            self.client.close()
        if self.server:
            self.server.close()
        self.root.destroy()

    def update_status(self):
        p = self.player
        if self.server:
            mode = "host %s:%d, igraca %d" % (self.host_ip, self.server.port, len(self.others) + 1)
        elif self.client:
            mode = "spojen na %s, igraca %d" % (self.client.address, len(self.others) + 1)
        else:
            mode = "singleplayer"
        text = "%s  FPS %4.1f  XYZ %5.1f %5.1f %5.1f  %dx%d  |  blok [%d] %s  |  %s" % (
            TITLE, self.fps, p.x, p.y, p.z, self.cols, self.rows,
            self.selected + 1, BLOCKS[HOTBAR[self.selected]].name, mode)
        if self.message:
            text += "  |  " + self.message
        self.status.configure(text=text)

    def on_focus_out(self, event):
        self.keys.clear()
        self.unlock_mouse()

    def screen_center(self):
        w, h = self.text_area.winfo_width(), self.text_area.winfo_height()
        return w // 2, h // 2

    def lock_mouse(self, event=None):
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

    def warp_mouse(self):
        x, y = self.screen_center()
        self.text_area.event_generate("<Motion>", warp=True, x=x, y=y)
        self.text_area.update_idletasks()

    def mouse_look(self):
        x, y = self.screen_center()
        mx = self.root.winfo_pointerx() - self.text_area.winfo_rootx()
        my = self.root.winfo_pointery() - self.text_area.winfo_rooty()
        dx, dy = mx - x, my - y
        if dx or dy:
            self.player.look(dx * MOUSE_SENSITIVITY, -dy * MOUSE_SENSITIVITY)
            self.warp_mouse()

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self.last_time, 0.25)
        self.last_time = now

        keys = self.keys
        turn = ("right" in keys) - ("left" in keys)
        tilt = ("up" in keys) - ("down" in keys)
        if turn or tilt:
            self.player.look(turn * LOOK_SPEED * dt, tilt * LOOK_SPEED * dt)
        if self.mouse_locked:
            self.mouse_look()
        self.player.update(dt, keys, self.world)
        if self.client:
            self.network(now)

        self.update_target()
        target = self.world.index(*self.target) if self.target else -1
        players = tuple((s[0], s[1], s[2], o["name"], pid) for pid, o in self.others.items()
                        for s in [o["state"]] if s)
        camera = self.player.camera() + (target, players)
        if camera != self.last_camera and self.cols:
            self.last_camera = camera
            self.draw(self.renderer.render(*camera))
            self.frames += 1
            self.frame_time += time.perf_counter() - now

        if now - self.fps_time >= 0.5:
            # FPS racunamo samo iz vremena crtanja (kad stojis, nista se ne crta)
            if self.frames:
                self.fps = self.frames / max(self.frame_time, 1e-6)
            self.frames, self.frame_time, self.fps_time = 0, 0.0, now
            self.update_status()

        spent = (time.perf_counter() - now) * 1000
        self.root.after(max(1, int(1000 / 60 - spent)), self.tick)

    def draw(self, chunks):
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", *chunks)
        self.text_area.update_idletasks()


def parse_address(text):
    host, _, port = text.strip().rpartition(":")
    if host and port.isdigit():
        return host, int(port)
    return text.strip(), net.PORT


class StartMenu:

    def __init__(self, root, name, on_start):
        self.root = root
        self.on_start = on_start
        self.servers = []
        self.searching = False
        look = {"bg": "black", "fg": "lightgreen", "font": (FONT_FAMILY, 12)}
        button = dict(look, bg="#1e1e1e", activebackground="#333333", activeforeground="white", width=34)

        self.frame = tk.Frame(root, bg="black")
        self.frame.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(self.frame, text=TITLE, bg="black", fg="lightgreen",
                 font=(FONT_FAMILY, 40, "bold")).pack(pady=(0, 18))

        row = tk.Frame(self.frame, bg="black")
        row.pack(pady=4)
        tk.Label(row, text="Ime:", **look).pack(side="left")
        self.name = tk.Entry(row, width=20, **dict(look, bg="#1e1e1e", insertbackground="white"))
        self.name.insert(0, name)
        self.name.pack(side="left", padx=6)

        tk.Button(self.frame, text="Igraj sam", command=self.solo, **button).pack(pady=(12, 4))
        tk.Button(self.frame, text="Napravi igru na mrezi (host)", command=self.host, **button).pack(pady=4)

        tk.Label(self.frame, text="Igre na lokalnoj mrezi:", **look).pack(pady=(16, 2))
        self.list = tk.Listbox(self.frame, height=5, width=46, **dict(look, bg="#1e1e1e",
                               selectbackground="#2e6b2e", highlightthickness=0))
        self.list.pack()
        self.list.bind("<Double-Button-1>", lambda e: self.join_selected())
        tk.Button(self.frame, text="Osvjezi popis", command=self.refresh, **button).pack(pady=(6, 2))
        tk.Button(self.frame, text="Spoji se na odabranu igru", command=self.join_selected, **button).pack(pady=2)

        row = tk.Frame(self.frame, bg="black")
        row.pack(pady=(14, 4))
        tk.Label(row, text="IP adresa:", **look).pack(side="left")
        self.address = tk.Entry(row, width=22, **dict(look, bg="#1e1e1e", insertbackground="white"))
        self.address.pack(side="left", padx=6)
        self.address.bind("<Return>", lambda e: self.join_address())
        tk.Button(self.frame, text="Spoji se na IP adresu", command=self.join_address, **button).pack(pady=2)

        self.info = tk.Label(self.frame, text="", bg="black", fg="orange", font=(FONT_FAMILY, 11))
        self.info.pack(pady=(12, 0))
        self.refresh()

    def player_name(self):
        return self.name.get().strip()[:16] or "Igrac"

    def say(self, text):
        self.info.configure(text=text)
        self.root.update_idletasks()

    def refresh(self):
        if self.searching:
            return
        self.searching = True
        self.say("trazim igre na mrezi...")
        result = []
        thread = threading.Thread(target=lambda: result.extend(net.discover()), daemon=True)
        thread.start()
        self.root.after(100, self.wait_for_search, thread, result)

    def wait_for_search(self, thread, result):
        if thread.is_alive():
            self.root.after(100, self.wait_for_search, thread, result)
            return
        self.searching = False
        if not self.frame.winfo_exists():
            return
        self.servers = result
        self.list.delete(0, tk.END)
        for ip, port, name, players in result:
            self.list.insert(tk.END, "%s  (%s:%d, igraca %d)" % (name, ip, port, players))
        self.say("pronadeno igara: %d" % len(result))

    def solo(self):
        self.start(None, None)

    def host(self):
        self.say("pokrecem server...")
        try:
            server = net.Server(self.player_name())
        except OSError as e:
            self.say("ne mogu pokrenuti server: %s" % e)
            return
        try:
            client = net.Client("127.0.0.1", server.port, self.player_name())
        except (OSError, ValueError) as e:
            server.close()
            self.say("ne mogu se spojiti na svoj server: %s" % e)
            return
        self.start(client, server)

    def join(self, host, port):
        self.say("spajam se na %s:%d..." % (host, port))
        try:
            client = net.Client(host, port, self.player_name())
        except (OSError, ValueError) as e:
            self.say("ne mogu se spojiti: %s" % e)
            return
        self.start(client, None)

    def join_selected(self):
        selection = self.list.curselection()
        if not selection:
            self.say("odaberi igru s popisa")
            return
        ip, port, _, _ = self.servers[selection[0]]
        self.join(ip, port)

    def join_address(self):
        if not self.address.get().strip():
            self.say("upisi IP adresu hosta")
            return
        self.join(*parse_address(self.address.get()))

    def start(self, client, server):
        self.frame.destroy()
        self.on_start(client, server)


def main():
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--name", default="Igrac%d" % random.randint(100, 999), help="ime igraca")
    parser.add_argument("--solo", action="store_true", help="odmah igraj sam")
    parser.add_argument("--host", action="store_true", help="odmah napravi igru na mrezi")
    parser.add_argument("--join", metavar="IP", help="odmah se spoji na igru (IP ili IP:port)")
    args = parser.parse_args()

    root = tk.Tk()
    root.title(TITLE)
    root.geometry("1200x700")
    root.configure(bg="black")

    def start(client, server):
        app = TkinterCraft(root, client, server)
        root.protocol("WM_DELETE_WINDOW", app.close)
        root.app = app

    if args.solo:
        start(None, None)
    elif args.host:
        server = net.Server(args.name)
        start(net.Client("127.0.0.1", server.port, args.name), server)
    elif args.join:
        host, port = parse_address(args.join)
        start(net.Client(host, port, args.name), None)
    else:
        StartMenu(root, args.name, start)
    root.mainloop()


if __name__ == "__main__":
    main()
