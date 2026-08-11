"""
Discord Müzik Botu — Railway Sürümü
-------------------------------------
Komutlar:
  /oynat [sorgu]   - Sesli kanala katılıp şarkı çalar
  /dur             - Müziği durdurur ve kanaldan ayrılır
  /atla            - Sonraki şarkıya geçer
  /kuyruk          - Kuyruktaki şarkıları listeler
  /ses [seviye]    - 0-100 arası ses seviyesi
  /duraklat        - Müziği duraklatır
  /devam           - Duraklatılmış müziği devam ettirir
  /temizle         - Kuyruğu temizler
"""

import asyncio
import json
import os
import urllib.request
import urllib.parse
from collections import deque

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# ---------------------------------------------------------------------------
# Opus
# ---------------------------------------------------------------------------
if not discord.opus.is_loaded():
    for lib in ['libopus.so.0', 'libopus.so', 'opus', 'libopus']:
        try:
            discord.opus.load_opus(lib)
            print(f"Opus yüklendi: {lib}", flush=True)
            break
        except Exception:
            continue

# ---------------------------------------------------------------------------
# Sabitler — Ortam değişkenlerinden oku
# ---------------------------------------------------------------------------
TOKEN           = os.environ.get("DISCORD_BOT_TOKEN", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
COOKIES_B64     = os.environ.get("COOKIES_B64", "")  # isteğe bağlı

# Geçici cookies dosyası oluştur (eğer env'den geldiyse)
COOKIES_PATH = ""
if COOKIES_B64:
    import base64, tempfile
    _tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb")
    _tmp.write(base64.b64decode(COOKIES_B64))
    _tmp.close()
    COOKIES_PATH = _tmp.name
    print(f"Cookies yüklendi: {COOKIES_PATH}", flush=True)

RENK_ANA    = 0x5865F2
RENK_BASARI = 0x57F287
RENK_HATA   = 0xED4245
RENK_BILGI  = 0xFEE75C

import shutil
import glob as _glob

def _ffmpeg_bul() -> str:
    """ffmpeg çalıştırılabilir dosyasını her yerde ara."""
    # 1) PATH içinde ara
    yol = shutil.which("ffmpeg")
    if yol:
        return yol
    # 2) Ortam değişkeni (start.sh tarafından ayarlanır)
    env_yol = os.environ.get("FFMPEG_LOCATION", "")
    if env_yol and os.path.exists(env_yol):
        return env_yol
    # 3) Yaygın sabit yollar
    for p in ("/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/bin/ffmpeg"):
        if os.path.exists(p):
            return p
    # 4) Nix store içinde ara (Railway/Nixpacks)
    for pat in ("/nix/store/*ffmpeg*/bin/ffmpeg", "/nix/store/*/bin/ffmpeg"):
        eslesenler = _glob.glob(pat)
        if eslesenler:
            return eslesenler[0]
    # 5) Bulunamazsa varsayılana düş (PATH'e güven)
    return "ffmpeg"

FFMPEG_PATH = _ffmpeg_bul()
print(f"ffmpeg yolu: {FFMPEG_PATH}", flush=True)

FFMPEG_OPTIONS = {
    "executable": FFMPEG_PATH,
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# ---------------------------------------------------------------------------
# YouTube Data API v3 ile arama
# ---------------------------------------------------------------------------
def youtube_ara(sorgu: str, max_sonuc: int = 5) -> list[dict]:
    if sorgu.startswith("http://") or sorgu.startswith("https://"):
        vid = None
        if "v=" in sorgu:
            vid = sorgu.split("v=")[1].split("&")[0]
        elif "youtu.be/" in sorgu:
            vid = sorgu.split("youtu.be/")[1].split("?")[0]
        if vid:
            return [{"id": vid, "title": sorgu, "channel": ""}]
        return []

    params = urllib.parse.urlencode({
        "part": "snippet",
        "q": sorgu,
        "type": "video",
        "videoCategoryId": "10",
        "maxResults": max_sonuc,
        "key": YOUTUBE_API_KEY,
    })
    url = f"https://www.googleapis.com/youtube/v3/search?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        sonuclar = []
        for item in data.get("items", []):
            vid_id = item.get("id", {}).get("videoId")
            if vid_id:
                snippet = item.get("snippet", {})
                sonuclar.append({
                    "id": vid_id,
                    "title": snippet.get("title", "Bilinmiyor"),
                    "channel": snippet.get("channelTitle", ""),
                })
        return sonuclar
    except Exception as e:
        print(f"YouTube API hatası: {e}", flush=True)
        return []

# ---------------------------------------------------------------------------
# yt-dlp ile ses URL'si al
# ---------------------------------------------------------------------------
PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://piped-api.garudalinux.org",
    "https://api.piped.privacyredirect.com",
    "https://pipedapi.in.projectsegfau.lt",
]

def piped_url_al(video_id: str) -> dict | None:
    """Piped API üzerinden ses URL'si al."""
    for instance in PIPED_INSTANCES:
        try:
            api_url = f"{instance}/streams/{video_id}"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())

            streams = data.get("audioStreams", [])
            if not streams:
                continue

            best = max(streams, key=lambda s: s.get("bitrate", 0))
            print(f"✅ Piped stream alındı ({instance}): {data.get('title')}", flush=True)
            return {
                "url":       best["url"],
                "title":     data.get("title", "Bilinmiyor"),
                "duration":  int(data.get("duration", 0)),
                "thumbnail": data.get("thumbnailUrl"),
                "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
            }
        except Exception as e:
            print(f"Piped hatası ({instance}): {e}", flush=True)
            continue
    return None

def ses_url_al(video_id: str) -> dict | None:
    yt_url = f"https://www.youtube.com/watch?v={video_id}"

    # Strategy 1: web client with po_token via bgutil (best for datacenter IPs)
    stratejiler = [
        {
            "extractor_args": {
                "youtube": {"player_client": ["web"]},
                "getpot_bgutil": {"baseurl": ["http://localhost:4416"]},
            }
        },
        {
            "extractor_args": {
                "youtube": {"player_client": ["tv_embedded"]},
                "getpot_bgutil": {"baseurl": ["http://localhost:4416"]},
            }
        },
        {
            "extractor_args": {
                "youtube": {"player_client": ["ios"]},
            }
        },
        {
            "extractor_args": {
                "youtube": {"player_client": ["android"]},
            }
        },
    ]

    for extra in stratejiler:
        client = list(extra["extractor_args"]["youtube"]["player_client"])[0]
        try:
            opts = {
                "format": "bestaudio/best",
                "noplaylist": True,
                "nocheckcertificate": True,
                "ignoreerrors": False,
                "quiet": True,
                "no_warnings": True,
                **extra,
            }
            if COOKIES_PATH:
                opts["cookiefile"] = COOKIES_PATH

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(yt_url, download=False)
                if info and info.get("url"):
                    print(f"✅ yt-dlp stream alındı [{client}]: {info.get('title')}", flush=True)
                    return {
                        "url":       info["url"],
                        "title":     info.get("title", "Bilinmiyor"),
                        "duration":  info.get("duration", 0),
                        "thumbnail": info.get("thumbnail"),
                        "webpage_url": yt_url,
                    }
        except Exception as e:
            print(f"yt-dlp hatası [{client}]: {e}", flush=True)
            continue

    print(f"⚠️ Tüm yöntemler başarısız: {video_id}", flush=True)
    return None

def bilgi_al(video_id: str, api_title: str = "") -> dict | None:
    sonuc = ses_url_al(video_id)
    if sonuc is None and api_title:
        return {
            "url": None,
            "title": api_title,
            "duration": 0,
            "thumbnail": None,
            "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
            "video_id": video_id,
        }
    if sonuc:
        sonuc["video_id"] = video_id
    return sonuc

# ---------------------------------------------------------------------------
# Bot kurulumu
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------------------------------------------------------------------------
# Sunucu başına oynatıcı durumu
# ---------------------------------------------------------------------------
class Oynatici:
    def __init__(self):
        self.kuyruk: deque[dict] = deque()
        self.suanki: dict | None = None
        self.ses_seviyesi: float = 0.5
        self.voice: discord.VoiceClient | None = None
        self.metin_kanal: discord.TextChannel | None = None

oynaticiler: dict[int, Oynatici] = {}

def oynatici_al(guild_id: int) -> Oynatici:
    if guild_id not in oynaticiler:
        oynaticiler[guild_id] = Oynatici()
    return oynaticiler[guild_id]

# ---------------------------------------------------------------------------
# Sonraki şarkıyı çal
# ---------------------------------------------------------------------------
async def sonraki_cal(guild_id: int):
    p = oynatici_al(guild_id)
    if not p.voice or not p.voice.is_connected():
        return

    if not p.kuyruk:
        p.suanki = None
        embed = discord.Embed(
            title="✅ Kuyruk bitti",
            description="Tüm şarkılar çalındı.",
            color=RENK_BILGI,
        )
        if p.metin_kanal:
            await p.metin_kanal.send(embed=embed)
        return

    sarki = p.kuyruk.popleft()

    if not sarki.get("url"):
        vid_id = sarki.get("video_id", "")
        yeni = await asyncio.get_event_loop().run_in_executor(None, ses_url_al, vid_id) if vid_id else None
        if yeni:
            sarki.update(yeni)
        else:
            if p.metin_kanal:
                await p.metin_kanal.send(
                    embed=discord.Embed(
                        title="⚠️ Atlandı",
                        description=f"**{sarki['title']}** akışı alınamadı, atlanıyor…",
                        color=RENK_HATA,
                    )
                )
            bot.loop.create_task(sonraki_cal(guild_id))
            return

    p.suanki = sarki

    def bitince(hata):
        if hata:
            print(f"FFmpeg hatası: {hata}", flush=True)
        bot.loop.create_task(sonraki_cal(guild_id))

    kaynak = discord.FFmpegPCMAudio(sarki["url"], **FFMPEG_OPTIONS)
    ses    = discord.PCMVolumeTransformer(kaynak, volume=p.ses_seviyesi)
    p.voice.play(ses, after=bitince)

    sure = sarki.get("duration", 0)
    sure_str = f"{sure//60}:{sure%60:02d}" if sure else "?"
    embed = discord.Embed(title="🎵 Şimdi Çalıyor", color=RENK_ANA)
    embed.add_field(name="Şarkı",  value=sarki["title"], inline=False)
    embed.add_field(name="Süre",   value=sure_str,       inline=True)
    if sarki.get("thumbnail"):
        embed.set_thumbnail(url=sarki["thumbnail"])
    if p.metin_kanal:
        await p.metin_kanal.send(embed=embed)

# ---------------------------------------------------------------------------
# Slash komutları
# ---------------------------------------------------------------------------

@tree.command(name="oynat", description="YouTube'dan şarkı çalar")
@app_commands.describe(sorgu="Şarkı adı veya YouTube URL'si")
async def oynat(interaction: discord.Interaction, sorgu: str):
    await interaction.response.defer(thinking=True)

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send(
            embed=discord.Embed(title="❌ Hata", description="Bir ses kanalında olmalısın.", color=RENK_HATA)
        )
        return

    p = oynatici_al(interaction.guild_id)
    p.metin_kanal = interaction.channel

    kanal = interaction.user.voice.channel
    if p.voice and p.voice.is_connected():
        if p.voice.channel.id != kanal.id:
            await p.voice.move_to(kanal)
    else:
        p.voice = await kanal.connect()

    await interaction.followup.send(
        embed=discord.Embed(description=f"🔍 **{sorgu}** aranıyor…", color=RENK_BILGI)
    )
    sonuclar = await asyncio.get_event_loop().run_in_executor(None, youtube_ara, sorgu)

    if not sonuclar:
        await interaction.channel.send(
            embed=discord.Embed(title="❌ Bulunamadı", description="Arama sonucu bulunamadı.", color=RENK_HATA)
        )
        return

    sarki = None
    for s in sonuclar:
        bilgi = await asyncio.get_event_loop().run_in_executor(None, bilgi_al, s["id"], s["title"])
        if bilgi:
            sarki = bilgi
            break

    if not sarki:
        await interaction.channel.send(
            embed=discord.Embed(title="❌ Hata", description="Video akışı alınamadı.", color=RENK_HATA)
        )
        return

    p.kuyruk.append(sarki)

    if not p.voice.is_playing() and not p.voice.is_paused():
        await sonraki_cal(interaction.guild_id)
    else:
        embed = discord.Embed(title="➕ Kuyruğa Eklendi", color=RENK_BASARI)
        embed.add_field(name="Şarkı", value=sarki["title"], inline=False)
        embed.add_field(name="Sıra",  value=str(len(p.kuyruk)), inline=True)
        await interaction.channel.send(embed=embed)


@tree.command(name="dur", description="Müziği durdurur ve kanaldan ayrılır")
async def dur(interaction: discord.Interaction):
    p = oynatici_al(interaction.guild_id)
    if p.voice and p.voice.is_connected():
        p.kuyruk.clear()
        p.suanki = None
        p.voice.stop()
        await p.voice.disconnect()
        p.voice = None
    await interaction.response.send_message(
        embed=discord.Embed(title="⏹️ Durduruldu", description="Kanaldan ayrıldım.", color=RENK_HATA)
    )


@tree.command(name="atla", description="Sonraki şarkıya geçer")
async def atla(interaction: discord.Interaction):
    p = oynatici_al(interaction.guild_id)
    if p.voice and p.voice.is_playing():
        p.voice.stop()
        await interaction.response.send_message(
            embed=discord.Embed(title="⏭️ Atlandı", color=RENK_BILGI)
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(title="❌", description="Şu an çalan bir şarkı yok.", color=RENK_HATA)
        )


@tree.command(name="duraklat", description="Müziği duraklatır")
async def duraklat(interaction: discord.Interaction):
    p = oynatici_al(interaction.guild_id)
    if p.voice and p.voice.is_playing():
        p.voice.pause()
        await interaction.response.send_message(
            embed=discord.Embed(title="⏸️ Duraklatıldı", color=RENK_BILGI)
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(title="❌", description="Çalan şarkı yok.", color=RENK_HATA)
        )


@tree.command(name="devam", description="Duraklatılmış müziği devam ettirir")
async def devam(interaction: discord.Interaction):
    p = oynatici_al(interaction.guild_id)
    if p.voice and p.voice.is_paused():
        p.voice.resume()
        await interaction.response.send_message(
            embed=discord.Embed(title="▶️ Devam Ediyor", color=RENK_BASARI)
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(title="❌", description="Duraklatılmış şarkı yok.", color=RENK_HATA)
        )


@tree.command(name="kuyruk", description="Kuyruktaki şarkıları listeler")
async def kuyruk_cmd(interaction: discord.Interaction):
    p = oynatici_al(interaction.guild_id)
    embed = discord.Embed(title="📋 Kuyruk", color=RENK_ANA)

    if p.suanki:
        embed.add_field(name="🎵 Şimdi Çalıyor", value=p.suanki["title"], inline=False)

    if p.kuyruk:
        liste = "\n".join(f"`{i+1}.` {s['title']}" for i, s in enumerate(list(p.kuyruk)[:10]))
        embed.add_field(name="Sıradaki Şarkılar", value=liste, inline=False)
    else:
        embed.add_field(name="Kuyruk", value="Boş", inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="ses", description="Ses seviyesini ayarlar (0-100)")
@app_commands.describe(seviye="Ses seviyesi (0-100)")
async def ses(interaction: discord.Interaction, seviye: int):
    if not 0 <= seviye <= 100:
        await interaction.response.send_message(
            embed=discord.Embed(title="❌", description="0-100 arası bir değer gir.", color=RENK_HATA)
        )
        return
    p = oynatici_al(interaction.guild_id)
    p.ses_seviyesi = seviye / 100
    if p.voice and p.voice.source:
        p.voice.source.volume = p.ses_seviyesi
    await interaction.response.send_message(
        embed=discord.Embed(
            title="🔊 Ses Seviyesi",
            description=f"Ses seviyesi **%{seviye}** olarak ayarlandı.",
            color=RENK_BASARI,
        )
    )


@tree.command(name="temizle", description="Kuyruğu temizler")
async def temizle(interaction: discord.Interaction):
    p = oynatici_al(interaction.guild_id)
    sayi = len(p.kuyruk)
    p.kuyruk.clear()
    await interaction.response.send_message(
        embed=discord.Embed(
            title="🗑️ Temizlendi",
            description=f"{sayi} şarkı kuyruktan silindi.",
            color=RENK_BILGI,
        )
    )

# ---------------------------------------------------------------------------
# Bot olayları
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    try:
        synced = await tree.sync()
        print(f"✅ {bot.user} olarak giriş yapıldı — {len(synced)} komut senkronize edildi.", flush=True)
    except Exception as e:
        print(f"Komut sync hatası: {e}", flush=True)

# ---------------------------------------------------------------------------
# Başlat
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN ortam değişkeni ayarlanmamış!")
    bot.run(TOKEN)
