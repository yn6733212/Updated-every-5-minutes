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
        extract_path = "bin"
        urllib.request.urlretrieve(url, archive_path)
        with tarfile.open(archive_path) as tar:
            tar.extractall(path=extract_path)
        for root, dirs, files in os.walk(extract_path):
            for file in files:
                if file == "ffmpeg":
                    os.rename(os.path.join(root, file), FFMPEG_PATH)
                    os.chmod(FFMPEG_PATH, 0o755)
                    break

HEBREW_UNITS = ["", "אַחַת", "שְׁתָיִם", "שָׁלֹשׁ", "אַרְבַּע", "חָמֵשׁ", "שֵׁשׁ", "שֶׁבַע", "שְׁמוֹנֶה", "תֵשַׁע"]
HEBREW_TENS = ["", "עֶשֶׂר", "עֶשְׂרִים", "שְׁלוֹשִׁים", "אַרְבָּעִים", "חֲמִשִׁים", "שִׁשִׁים", "שִׁבְעִים", "שְׁמוֹנִים", "תִשְׁעִים"]
HEBREW_TEENS = ["עֶשֶׂר", "אֵחָד עֶשְׂרֵה", "שְׁתֵים עֶשְׂרֵה", "שְׁלֹשׁ עֶשְׂרֵה", "אַרְבַּע עֶשְׂרֵה", "חָמֵשׁ עֶשְׂרֵה", "שֵׁשׁ עֶשְׂרֵה", "שְׁבַע עֶשְׂרֵה", "שְׁמוֹנֶה עֶשְׂרֵה", "תְשַׁע עֶשְׂרֵה"]
HEBREW_THOUSANDS = ["", "אֶלֶף", "אַלְפָיִם", "שְׁלוֹשְׁת אַלָפִים", "אַרְבַּעַת אַלָפִים", "חֲמֵשְׁת אַלָפִים", "שֵׁשְׁת אַלָפִים", "שְׁבָת אַלָפִים", "שְׁמוֹנַת אַלָפִים", "תְשָׁת אַלָפִים"]

def number_to_hebrew(n):
    if n == 0:
        return "אֵפֵס"
    if 10 < n < 20:
        return HEBREW_TEENS[n - 10]
    tens = n // 10
    units = n % 10
    parts = []
    if tens:
        parts.append(HEBREW_TENS[tens])
    if units:
        if tens:
            parts.append("ו" + HEBREW_UNITS[units])
        else:
            parts.append(HEBREW_UNITS[units])
    return " ".join(parts)

def format_number_hebrew(number):
    try:
        number = float(number)
        if number >= 1000 and not number.is_integer():
            number = round(number)
        if number.is_integer():
            number = int(number)
            if number >= 1000:
                thousands = number // 1000
                rest = number % 1000
                if 1 <= thousands < 10:
                    thousands_text = HEBREW_THOUSANDS[thousands]
                else:
                    thousands_text = number_to_hebrew(thousands) + " אֶלֶף"
                rest_text = number_to_hebrew(rest) if rest else ""
                return f"{thousands_text} ו{rest_text}" if rest_text else thousands_text
            else:
                return number_to_hebrew(number)
        else:
            parts = str(number).split(".")
            whole = int(parts[0])
            decimal = int(parts[1][:2])
            return f"{format_number_hebrew(whole)} נְקוּדָה {number_to_hebrew(decimal)}"
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
        intro = f"{name} אֵחָד שָבֵה לֵ {current} שְקָלִים."
    elif type_ == "commodity":
        intro = f"{name} נסחר כָּעֵת בֵּשָׁעָר של {current} דוֹלָר."
    else:
        intro = f"{name} ֵּנסחר כעת ב{current}"

    full_text = (
        f"{intro} "
        f"{data['change_day']}. "
        f"{data['change_week']}. "
        f"{data['change_3m']}. "
        f"{data['change_year']}. "
        f"הָמֵחִיר הָנוֹכֵחִי רָחוֹק מֵהָשִׂיא ב{from_high} אָחוּז."
    )
    print(f"📜 טקסט עבור {name}: {full_text}")
    return full_text

def is_same_text(symbol, new_text):
    filename = f"last_text_{symbol.replace('^','')}.txt"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            old_text = f.read()
            if old_text.strip() == new_text.strip():
                return True
    with open(filename, "w", encoding="utf-8") as f:
        f.write(new_text)
    return False

async def text_to_speech(text, filename):
    communicate = Communicate(text, voice="he-IL-AvriNeural", rate="-10%")
    await communicate.save(filename)

def convert_to_wav(mp3_file, wav_file):
    ensure_ffmpeg()
    with open(os.devnull, 'w') as devnull:
        subprocess.run(
            [FFMPEG_PATH, "-y", "-i", mp3_file, "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le", wav_file],
            stdout=devnull,
            stderr=devnull
        )

def upload_to_yemot(wav_file, path):
    m = MultipartEncoder(fields={
        'token': TOKEN,
        'path': path + "001.wav",
        'file': ("001.wav", open(wav_file, 'rb'), 'audio/wav')
    })
    requests.post("https://www.call2all.co.il/ym/api/UploadFile", data=m, headers={'Content-Type': m.content_type})

def is_today_in_history(hist):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return today_str in hist.index.strftime("%Y-%m-%d")

def format_change(from_, to, prefix, trading_day_exists=True):
    percent = round((to - from_) / from_ * 100, 2)
    if prefix == "מתחילת היום" and not trading_day_exists:
        return "הבורסה טרם נפתחה – הנתונים הם מיום המסחר האחרון."
    direction = "עלייה" if percent > 0 else "ירידה"
    return f"{prefix} נרשמה {direction} של {format_number_hebrew(abs(percent))} אחוז"

def get_stock_data(symbol):
    t = yf.Ticker(symbol)
    hist = t.history(period="1y")
    if hist.empty:
        return None

    trading_day_exists = is_today_in_history(hist)
    today = hist.iloc[-1]["Close"]
    if not trading_day_exists and len(hist) >= 2:
        yesterday = hist.iloc[-2]["Close"]
    else:
        yesterday = hist.iloc[-2]["Close"] if len(hist) >= 2 else today

    week = hist.iloc[-5]["Close"] if len(hist) >= 5 else today
    quarter = hist.iloc[-60]["Close"] if len(hist) >= 60 else today
    year = hist.iloc[0]["Close"]
    high = hist["Close"].max()
    from_high = round((high - today) / high * 100, 2)

    return {
        "current": today,
        "change_day": format_change(yesterday, today, "מתחילת היום", trading_day_exists),
        "change_week": format_change(week, today, "מתחילת השבוע"),
        "change_3m": format_change(quarter, today, "בשלושת החודשים האחרונים"),
        "change_year": format_change(year, today, "מתחילת השנה"),
        "from_high": from_high
    }

async def main():
    print("🚀 ריצה חד־פעמית התחילה...")
    with open(ASSETS_FILE, "r", encoding="utf-8") as f:
        assets = json.load(f)

    for asset in assets:
        symbol = asset["symbol"]
        name = asset["name"]
        path = asset["target_path"]

        print(f"📈 {name} ({symbol})...")
        data = get_stock_data(symbol)
        if data is None:
            continue

        text = create_text(asset, data)

        if is_same_text(symbol, text):
            print("⚠️ תוצאה זהה – מדלג")
            continue

        await text_to_speech(text, "temp.mp3")
        convert_to_wav("temp.mp3", "temp.wav")
        upload_to_yemot("temp.wav", path)
        print(f"✅ הועלה לשלוחה {path}")

if __name__ == "__main__":
    async def loop_forever():
        while True:
            print("⏱️ התחלה חדשה של ריצה...")
            try:
                await main()
            except Exception as e:
                print(f"❌ שגיאה בריצה: {e}")
            print("⏳ ממתין 10 דקות לריצה הבאה...\n")
            await asyncio.sleep(10 * 60)

    asyncio.run(loop_forever())
