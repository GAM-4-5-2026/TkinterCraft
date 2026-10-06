import base64
import json
import math
import queue
import socket
import threading
import time
import zlib

from objects import BEDROCK, BLOCKS
from world import World

PORT = 25565
DISCOVERY_PORT = 25566
DISCOVERY_HELLO = b"TKINTERCRAFT?"
MAX_LINE = 1 << 16


def send_line(sock, message):
    sock.sendall((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))


def encode_world(world):
    data = base64.b64encode(zlib.compress(bytes(world.blocks))).decode("ascii")
    return {"width": world.width, "depth": world.depth, "height": world.height,
            "seed": world.seed, "blocks": data}


def decode_world(message):
    w, d, h = int(message["width"]), int(message["depth"]), int(message["height"])
    blocks = zlib.decompress(base64.b64decode(message["blocks"]))
    if len(blocks) != w * d * h:
        raise ValueError("krivi podaci o svijetu")
    return World(w, d, h, int(message["seed"]), blocks=blocks)


def local_ip():
    # nista se ne salje, samo saznajemo kojom adresom racunalo izlazi na mrezu
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def discover(timeout=1.0):
    """Trazi servere na lokalnoj mrezi. Vraca listu (ip, port, ime, broj igraca)."""
    found = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(0.2)
    for address in ("<broadcast>", "127.0.0.1"):
        try:
            s.sendto(DISCOVERY_HELLO, (address, DISCOVERY_PORT))
        except OSError:
            pass
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            data, (ip, _) = s.recvfrom(1024)
            info = json.loads(data)
            found[ip] = (ip, int(info["port"]), str(info["name"]), int(info["players"]))
        except socket.timeout:
            continue
        except (OSError, ValueError, KeyError, TypeError):
            break
    s.close()
    servers = list(found.values())
    # isti server se javi i preko 127.0.0.1 i preko mrezne adrese
    if len(servers) > 1:
        servers = [s for s in servers if s[0] != "127.0.0.1"]
    return servers


class Server:
    """Server pokrenut kod igraca koji hosta. Cuva svijet i prosljeduje poruke."""

    def __init__(self, name, port=PORT):
        self.name = name
        self.port = port
        self.world = World()
        self.lock = threading.Lock()
        self.clients = {}
        self.owner = None
        self.next_id = 1
        self.listener = socket.create_server(("", port))
        threading.Thread(target=self._accept_loop, daemon=True).start()
        try:
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp.bind(("", DISCOVERY_PORT))
            threading.Thread(target=self._discovery_loop, daemon=True).start()
        except OSError:
            self.udp = None

    def close(self):
        for sock in [self.listener, self.udp] + [c["sock"] for c in list(self.clients.values())]:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

    def _accept_loop(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _discovery_loop(self):
        while True:
            try:
                data, address = self.udp.recvfrom(256)
            except OSError:
                return
            if data == DISCOVERY_HELLO:
                info = {"name": self.name, "port": self.port, "players": len(self.clients)}
                try:
                    self.udp.sendto(json.dumps(info).encode("utf-8"), address)
                except OSError:
                    pass

    def _broadcast(self, message, skip=None):
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        for pid, client in list(self.clients.items()):
            if pid != skip:
                try:
                    client["sock"].sendall(data)
                except OSError:
                    pass

    def _serve(self, conn):
        reader = conn.makefile("r", encoding="utf-8", newline="\n")
        pid = None
        try:
            hello = json.loads(reader.readline(MAX_LINE))
            name = str(hello.get("name") or "Igrac")[:16]
            with self.lock:
                pid = self.next_id
                self.next_id += 1
                if self.owner is None:
                    self.owner = pid
                players = [{"id": i, "name": c["name"], "state": c["state"]} for i, c in self.clients.items()]
                send_line(conn, {"t": "welcome", "id": pid, "world": encode_world(self.world), "players": players})
                self.clients[pid] = {"sock": conn, "name": name, "state": None}
                self._broadcast({"t": "join", "id": pid, "name": name}, skip=pid)
            while True:
                line = reader.readline(MAX_LINE)
                if not line.endswith("\n"):
                    break
                self._handle(pid, json.loads(line))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        finally:
            with self.lock:
                if self.clients.pop(pid, None):
                    self._broadcast({"t": "leave", "id": pid})
            conn.close()

    def _handle(self, pid, message):
        kind = message.get("t")
        if kind == "pos":
            state = [float(v) for v in message["s"]]
            if len(state) != 5 or not all(math.isfinite(v) for v in state):
                return
            with self.lock:
                self.clients[pid]["state"] = state
                self._broadcast({"t": "pos", "id": pid, "s": state}, skip=pid)
        elif kind == "set":
            x, y, z, block = (int(message[k]) for k in "xyzb")
            if not 0 <= block < len(BLOCKS) or block == BEDROCK:
                return
            with self.lock:
                if not self.world.inside(x, y, z) or self.world.get(x, y, z) == BEDROCK:
                    return
                self.world.set(x, y, z, block)
                # saljemo i onome tko je promijenio, da svi imaju isti redoslijed promjena
                self._broadcast({"t": "set", "x": x, "y": y, "z": z, "b": block})
        elif kind == "regen" and pid == self.owner:
            with self.lock:
                self.world = World()
                self._broadcast({"t": "world", "world": encode_world(self.world)})


class Client:
    """Veza prema serveru. Poruke se citaju u pozadini i skupljaju u red."""

    def __init__(self, host, port, name):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        reader = self.sock.makefile("r", encoding="utf-8", newline="\n")
        send_line(self.sock, {"t": "hello", "name": name})
        welcome = json.loads(reader.readline())
        if welcome.get("t") != "welcome":
            raise ValueError("server nije poslao svijet")
        self.sock.settimeout(None)
        self.address = "%s:%d" % (host, port)
        self.id = welcome["id"]
        self.world = decode_world(welcome["world"])
        self.players = welcome["players"]
        self.connected = True
        self.inbox = queue.Queue()
        self.send_lock = threading.Lock()
        threading.Thread(target=self._read_loop, args=(reader,), daemon=True).start()

    def _read_loop(self, reader):
        try:
            for line in reader:
                self.inbox.put(json.loads(line))
        except (OSError, ValueError):
            pass
        self.inbox.put({"t": "disconnect"})

    def send(self, message):
        with self.send_lock:
            try:
                send_line(self.sock, message)
            except OSError:
                self.connected = False

    def poll(self):
        while True:
            try:
                yield self.inbox.get_nowait()
            except queue.Empty:
                return

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
