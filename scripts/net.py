import json
import queue
import socket
import threading
import time

from game import Game
from world import World, world_from_message

PORT = 25565
DISCOVERY_PORT = 25566
DISCOVERY_HELLO = b"TKINTERCRAFT?"
MAX_LINE = 65536
VERSION = 3


def send_line(sock, message):
    text = json.dumps(message, separators=(",", ":")) + "\n"
    sock.sendall(text.encode("utf-8"))


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    s.close()
    return ip


# trazi igre na mrezi (posalje poruku svima i ceka odgovor)
def discover(timeout=1.0):
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
            data, sender = s.recvfrom(1024)
            info = json.loads(data)
            ip = sender[0]
            found[ip] = (ip, int(info["port"]), str(info["name"]), int(info["players"]))
        except socket.timeout:
            continue
        except (OSError, ValueError, KeyError, TypeError):
            break
    s.close()
    servers = []
    for ip in found:
        servers.append(found[ip])
    if len(servers) > 1:
        without_local = []
        for server in servers:
            if server[0] != "127.0.0.1":
                without_local.append(server)
        servers = without_local
    return servers


class Server:

    def __init__(self, name, port=PORT):
        self.name = name
        self.port = port
        self.lock = threading.Lock()
        self.clients = {}
        self.next_id = 1
        self.game = Game(World(), self.emit)
        self.listener = socket.create_server(("", port))
        self.running = True
        threading.Thread(target=self.accept_loop, daemon=True).start()
        threading.Thread(target=self.tick_loop, daemon=True).start()
        try:
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp.bind(("", DISCOVERY_PORT))
            threading.Thread(target=self.discovery_loop, daemon=True).start()
        except OSError:
            self.udp = None

    def close(self):
        self.running = False
        for pid in list(self.clients):
            try:
                self.clients[pid].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.clients[pid].close()
        self.listener.close()
        if self.udp:
            self.udp.close()

    def emit(self, message, to=None, skip=None):
        if message.get("t") == "world" and isinstance(message["world"], World):
            new_message = {}
            for key in message:
                new_message[key] = message[key]
            new_message["world"] = message["world"].to_message()
            message = new_message
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        if to is None:
            targets = list(self.clients)
        else:
            targets = [to]
        for pid in targets:
            if pid in self.clients and pid != skip:
                try:
                    self.clients[pid].sendall(data)
                except OSError:
                    pass

    def tick_loop(self):
        last = time.perf_counter()
        while self.running:
            time.sleep(0.1)
            now = time.perf_counter()
            with self.lock:
                self.game.update(now - last)
            last = now

    def accept_loop(self):
        while True:
            try:
                conn, address = self.listener.accept()
            except OSError:
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    def discovery_loop(self):
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

    def serve(self, conn):
        reader = conn.makefile("r", encoding="utf-8", newline="\n")
        pid = None
        try:
            hello = json.loads(reader.readline(MAX_LINE))
            if hello.get("v") != VERSION:
                send_line(conn, {"t": "error", "text": "razlicita verzija igre kod tebe i hosta"})
                return
            name = hello.get("name")
            if not name:
                name = "Igrac"
            name = str(name)[:16]
            with self.lock:
                pid = self.next_id
                self.next_id += 1
                self.game.add_player(pid, name)
                welcome = self.game.welcome(pid)
                welcome["t"] = "welcome"
                welcome["world"] = self.game.world.to_message()
                send_line(conn, welcome)
                self.clients[pid] = conn
                self.game.announce(pid)
            while True:
                line = reader.readline(MAX_LINE)
                if not line.endswith("\n"):
                    break
                message = json.loads(line)
                with self.lock:
                    self.game.handle(pid, message)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        finally:
            with self.lock:
                if pid in self.clients:
                    del self.clients[pid]
                    self.game.remove_player(pid)
            conn.close()


class Client:

    def __init__(self, host, port, name):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        reader = self.sock.makefile("r", encoding="utf-8", newline="\n")
        send_line(self.sock, {"t": "hello", "name": name, "v": VERSION})
        welcome = json.loads(reader.readline())
        if welcome.get("t") == "error":
            raise ValueError(welcome.get("text"))
        if welcome.get("t") != "welcome":
            raise ValueError("server nije poslao svijet")
        self.sock.settimeout(None)
        self.address = f"{host}:{port}"
        self.id = welcome["id"]
        self.world = world_from_message(welcome["world"])
        del welcome["world"]
        self.welcome = welcome
        self.connected = True
        self.inbox = queue.Queue()
        self.send_lock = threading.Lock()
        threading.Thread(target=self.read_loop, args=(reader,), daemon=True).start()

    def read_loop(self, reader):
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
        messages = []
        while not self.inbox.empty():
            messages.append(self.inbox.get())
        return messages

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
