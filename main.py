import json
import yfinance as yf
import asyncio
import datetime
import os
import subprocess
from edge_tts import Communicate
from requests_toolbelt.multipart.encoder import MultipartEncoder
import requests
import urllib.request
import tarfile
import pytz
import warnings

warnings.filterwarnings("ignore")

USERNAME = "0733181201"
PASSWORD = "6714453"
TOKEN = f"{USERNAME}:{PASSWORD}"
ASSETS_FILE = "assets.json"
FFMPEG_PATH = "./bin/ffmpeg"

def ensure_ffmpeg():
    if not os.path.exists(FFMPEG_PATH):
        print("⬇️ מוריד ffmpeg...")
        os.makedirs("bin", exist_ok=True)
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        archive_path = "bin/ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, archive_path)
        with tarfile.open(archive_path) as tar:
            tar.extractall(path="bin")
        for root, dirs, files in os.walk("bin"):
            for file in files:
                if file == "ffmpeg":
                    os.rename(os.path.join(root, file), FFMPEG_PATH)
                    os.chmod(FFMPEG_PATH, 0o755)
                    break

def should_run(asset):
    interval = asset.get("interval", "10m")
    last_run_str = asset.get("last_run", "2000-01-01T00:00:00")
    last_run = datetime.datetime.fromisoformat(last_run_str)
    now = datetime.datetime.now()
    delta = now - last_run

    amount = int(interval[:-1])
    unit = interval[-1]

    if unit == "s":
        return delta.total_seconds() >= amount
    elif unit == "m":
        return delta.total_seconds() >= amount * 60
    elif unit == "h":
        return delta.total_seconds() >= amount * 3600
    return False

def update_last_run(asset):
    asset["last_run"] = datetime.datetime.now().replace(microsecond=0).isoformat()

HEBREW_UNITS = ["", "אַחַת", "שְׁתָיִים", "שָׁלוֹשׁ", "אַרְבַּע", "חָמֵשׁ", "שֵׁשׁ", "שֶׁבַע", "שְׁמוֹנֶה", "תֵשַׁע"]
HEBREW_TENS = ["", "עֶשֶׂר", "עֶשְׂרִים", "שְׁלוֹשִׁים", "אַרְבָּעִים", "חֲמִשִּׁים", "שִׁשִּׁים", "שִׁבְעִים", "שְׁמוֹנִים", "תִשְׁעִים"]
HEBREW_TEENS = ["עֶשֶׂר", "אֵחָד עֶשְׂרֵה", "שְׁתֵים עֶשְׂרֵה", "שָׁלוֹשׁ עֶשְׂרֵה", "אַרְבַּע עֶשְׂרֵה", "חָמֵשׁ עֶשְׂרֵה", "שֵׁשׁ עֶשְׂרֵה", "שֶׁבַע עֶשְׂרֵה", "שְׁמוֹנֶה עֶשְׂרֵה", "תֵשַׁע עֶשְׂרֵה"]

def number_to_hebrew(n):
    if n == 0:
        return "אֵפֶס"
    if 10 < n < 20:
        return HEBREW_TEENS[n - 10]
    tens = n // 10
    units = n % 10
    parts = []
    if tens:
        parts.append(HEBREW_TENS[tens])
    if units:
        parts.append("ו" + HEBREW_UNITS[units] if tens else HEBREW_UNITS[units])
    return " ".join(parts)

def format_number_hebrew(number):
    try:
        number = float(number)
        if number >= 1000 and not number.is_integer():
            number = round(number)
        if number.is_integer():
            number = int(number)
            return number_to_hebrew(number)
        parts = str(number).split(".")
        whole = int(parts[0])
        decimal = int(parts[1][:2])
        return f"{number_to_hebrew(whole)} נְקוּדָה {number_to_hebrew(decimal)}"
    except:
        return str(number)

def create_text(asset, data):
    name = asset["name"]
    type_ = asset["type"]
    currency = "שְקָלִים" if type_ == "stock_il" else "דוֹלָר"
    unit = "נֵקוּדוֹת" if type_ in ["index", "sector"] else currency
    current = format_number_hebrew(data['current'])
    from_high = format_number_hebrew(data['from_high'])

    if type_ == "index":
        intro = f"מָדָד {name} עומד כָּעֵת על {current} {unit}."
    elif type_ == "sector":
        intro = f"סֵקְטוֹר {name} עוֹמֵד כָּעֵת על {current} {unit}."
    elif type_ == "stock_il":
        intro = f"מֵנָיָת {name} נִסְחֵרֵת כָּעֵת בֵּשׁוֹבִי שֵׁל {current} {unit}."
    elif type_ == "stock_us":
        intro = f"מֵנָיָת {name} נִסְחֵרֵת כָּעֵת בֵּשׁוֹבִי שֵׁל {current} {unit}."
    elif type_ == "crypto":
        intro = f"מָטְבֵּע {name} נסחר כָּעֵת בֵּשָׁעָר שֵׁל {current} דוֹלָר."
    elif type_ == "forex":
        intro = f"{name} אֵחָד שָוֵה לֵ־{current} שְקָלִים."
    elif type_ == "commodity":
        intro = f"{name} נסחר כָּעֵת בֵּשָׁעָר של {current} דוֹלָר."
    else:
        intro = f"{name} נסחר כעת ב{current}"

    return (
        f"{intro} "
        f"{data['change_day']}. "
        f"{data['change_week']}. "
        f"{data['change_3m']}. "
        f"{data['change_year']}. "
        f"המחיר הנוכחי רחוק מהשיא ב{from_high} אחוז."
    )

async def text_to_speech(text, filename):
    communicate = Communicate(text, voice="he-IL-AvriNeural", rate="-10%")
    await communicate.save(filename)

def convert_to_wav(mp3_file, wav_file):
    ensure_ffmpeg()
    subprocess.run(
        [FFMPEG_PATH, "-y", "-i", mp3_file, "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le", wav_file],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def upload_to_yemot(wav_file, path):
    m = MultipartEncoder(fields={
        'token': TOKEN,
        'path': path + "001.wav",
        'file': ("001.wav", open(wav_file, 'rb'), 'audio/wav')
    })
    requests.post("https://www.call2all.co.il/ym/api/UploadFile", data=m, headers={'Content-Type': m.content_type})

def format_change(from_, to, prefix):
    percent = round((to - from_) / from_ * 100, 2)
    direction = "עלייה" if percent > 0 else "ירידה"
    return f"{prefix} נרשמה {direction} של {format_number_hebrew(abs(percent))} אחוז"

def get_stock_data(symbol):
    t = yf.Ticker(symbol)
    hist = t.history(period="1y")
    if hist.empty:
        return None
    today = hist.iloc[-1]["Close"]
    yesterday = hist.iloc[-2]["Close"] if len(hist) >= 2 else today
    week = hist.iloc[-5]["Close"] if len(hist) >= 5 else today
    quarter = hist.iloc[-60]["Close"] if len(hist) >= 60 else today
    year = hist.iloc[0]["Close"]
    high = hist["Close"].max()
    from_high = round((high - today) / high * 100, 2)

    return {
        "current": today,
        "change_day": format_change(yesterday, today, "מתחילת היום"),
        "change_week": format_change(week, today, "מתחילת השבוע"),
        "change_3m": format_change(quarter, today, "בשלושת החודשים האחרונים"),
        "change_year": format_change(year, today, "מתחילת השנה"),
        "from_high": from_high
    }

async def main():
    with open(ASSETS_FILE, "r", encoding="utf-8") as f:
        assets = json.load(f)

    for asset in assets:
        if not should_run(asset):
            continue

        symbol = asset["symbol"]
        path = asset["target_path"]
        name = asset["name"]

        print(f"🎯 {name} ({symbol}) – מריץ...")

        data = get_stock_data(symbol)
        if not data:
            print(f"⚠️ לא נמצאו נתונים עבור {symbol}")
            continue

        text = create_text(asset, data)
        await text_to_speech(text, "temp.mp3")
        convert_to_wav("temp.mp3", "temp.wav")
        upload_to_yemot("temp.wav", path)
        print(f"✅ הועלה לשלוחה {path}")
        update_last_run(asset)

    with open(ASSETS_FILE, "w", encoding="utf-8") as f:
        json.dump(assets, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    async def loop_forever():
        while True:
            try:
                await main()
            except Exception as e:
                print(f"❌ שגיאה: {e}")
            await asyncio.sleep(60)

    asyncio.run(loop_forever())
