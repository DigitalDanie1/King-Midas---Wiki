#!/usr/bin/env python3
import base64
import csv
import io
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SOURCE_DIR = DATA_DIR / "sources"
CSV_PATH = DATA_DIR / "games.csv"
HTML_PATH = ROOT / "index.html"

SOURCE_FILES = [
    SOURCE_DIR / "KingMidas Games Wiki - KM Games DB.csv",
    SOURCE_DIR / "KingMidas Games Wiki - NEXT-GEN.csv",
    SOURCE_DIR / "KingMidas Games Wiki - SLOT FEATURES.csv",
    SOURCE_DIR / "KingMidas Games Wiki - Retired_Hidden Games.csv",
    SOURCE_DIR / "KingMidas Games Wiki - UFA Exclusive Games.csv",
]
STATUS_FILE = SOURCE_DIR / "KingMidas Games Wiki - Status Definitions.csv"

LANG_COLUMNS = {
    "EN": "Product Name EN",
    "CN": "Product Name CN",
    "HANT": "Product Name HANT",
    "TH": "Product Name TH",
    "VN": "Product Name VN",
    "ID": "Product Name ID",
    "KR": "Product Name KR",
    "MY": "Product Name MY",
    "PTBR": "Product Name PTBR",
    "ESLA": "Product Name ESLA",
    "RU": "Product Name RU",
    "TR": "Product Name TR",
    "BN": "Product Name BN",
    "HI": "Product Name HI",
}

FEATURE_COLUMNS = [
    "Buy Feature",
    "Free Spin",
    "Respin",
    "Retrigger",
    "Lucky Draw",
    "Multiplier Bonus",
    "Hold & Spin",
    "Multiplier Symbol",
    "Increasing Multiplier",
    "Featured Wild",
    "Progressive Jackpot",
    "Fixed Jackpot",
    "Double Chance feature",
    "Instant Play",
    "Gamification Compatibility",
]

FIELDNAMES = [
    "collection",
    "identifier",
    "name",
    "names",
    "studio",
    "gid",
    "exclusivity",
    "status",
    "firstLive",
    "icon",
    "logo",
    "rtp",
    "highestPayout",
    "maxWin",
    "volatility",
    "commission",
    "hitRate",
    "genre",
    "mechanic",
    "bonus",
    "tags",
    "originated",
    "countryDAU",
    "themes",
    "market",
    "additionalMarket",
    "countryFilter",
    "display",
    "gameType",
    "winTiers",
    "gamification",
    "designTheme",
    "description",
    "gameFeatures",
    "reels",
    "payways",
    "demo",
    "asiaDemo",
    "gameSetting",
    "localisation",
    "cert",
    "currency",
    "service",
    "features",
    "languages",
    "integrations",
    "sizes",
    "assets",
    "variant",
    "variantDesc",
    "image_source",
]

JSON_COLUMNS = {"names", "tags", "cert", "features", "languages", "integrations", "sizes", "assets"}

IMAGE_FALLBACKS = {
    "tekken-8": "https://cdn.akamai.steamstatic.com/steam/apps/1778820/header.jpg",
    "coin-pusher-pirates": "https://publiccdn.kingmidasgames.net/500x500images/KingMidas/coin-pusher_500x500_en.jpg",
    "judi-kolok-kolok": "https://publiccdn.kingmidasgames.net/500x500images/KingMidas/belangkai-2_500x500_en.jpg",
    "chicken-crossy-z": "https://publiccdn.kingmidasgames.net/500x500images/KingMidas/chicken-crossy_500x500_en.jpg",
    "mega-fishing": "https://wbgame.tadagaming.com/All-In-One/production/img/tadaPlusPlayer/games/TaDa_games_introImg_74_en-us.webp",
    "wild-train-heist": "https://images.prismic.io/fanduel-casino/Z3O-_JbqstJ985ut_WildWildWestTheGreatTrainHeist_logo.png?auto=format%2Ccompress&w=225&h=225",
    "km-captain-loot": "https://one-game.com/wp-content/uploads/2025/06/CaptianLoot_thumb_new-300x300.jpg",
    "km-captain-loot-mega-chance": "https://one-game.com/wp-content/uploads/2025/06/CaptianLootMegaChance_thumb_new-300x300.jpg",
    "km-get-that-gold": "https://one-game.com/wp-content/uploads/2025/10/GetThatGold_thumb_new-300x300.jpg",
    "km-spooky-and-sexy": "https://one-game.com/wp-content/uploads/2026/03/SpookyAndSexy_thunb_new-300x300.jpg",
    "xoc-dia": "https://publiccdn.kingdomhall729.com/500x500images/KingMidas/xoc-dia-2_500x500_en.jpg",
    "fan-tan-2": "https://publiccdn.kingmidasgames.net/500x500images/KingMidas/fan-tan-3_500x500_en.jpg",
}

NAME_FIXES = {
    "tekken-8": "Tekken 8",
    "coin-pusher-pirates": "Coin Pusher Pirates",
    "mega-fishing": "Mega Fishing",
    "km-captain-loot-mega-chance": "Captain Loot Mega Chance",
    "km-spooky-and-sexy": "Spooky & Sexy",
}

STATUS_COLORS = {
    "Live": "var(--live)",
    "Under Development": "var(--dev)",
    "Production Ready": "var(--prod)",
    "Integrated": "var(--integrated)",
    "Retired": "var(--retired)",
    "Maintenance": "var(--maint)",
    "Not Started": "var(--notstarted)",
    "On Hold": "var(--maint)",
    "Copyright Game": "var(--copyright)",
}

DEFAULT_STATUS_DEFS = {
    "Live": "The game has launched and is playable on the operator's site.",
    "Under Development": "The game is currently in development, including art, GDD, QA, or related production work.",
    "Production Ready": "The product is completed and QA-tested, but is still pending integration with the aggregator.",
    "Integrated": "The product has been integrated with the aggregator, but has not yet gone live.",
    "Retired": "The product has been permanently taken down.",
    "Maintenance": "The product is temporarily offline for fixes, updates, or maintenance work.",
    "Not Started": "The product is in a very early concept stage, with only initial ideas defined.",
    "On Hold": "The product is put on hold until further notice.",
    "Copyright Game": "Copyright-restricted.",
}


def clean(value):
    value = "" if value is None else str(value)
    value = value.strip()
    return "" if value in {"N.A", "N/A", "n.a", "na"} else value


def norm_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def get(row, *aliases):
    normalized = {norm_key(k): v for k, v in row.items() if k is not None}
    for alias in aliases:
        key = norm_key(alias)
        if key in normalized:
            value = clean(normalized[key])
            if value:
                return value
    return ""


def truthy(value):
    return clean(value).lower() in {"true", "yes", "y", "1", "✓", "check", "checked"}


def slug(value, fallback):
    base = clean(value) or clean(fallback) or "game"
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")


def normalize_status(value):
    value = clean(value)
    if not value:
        return "Not Started"
    aliases = {
        "launched": "Live",
        "live": "Live",
        "underdevelopment": "Under Development",
        "productionready": "Production Ready",
        "integrated": "Integrated",
        "retired": "Retired",
        "maintenance": "Maintenance",
        "notstarted": "Not Started",
        "onhold": "On Hold",
    }
    return aliases.get(norm_key(value), value)


def normalize_genre(value):
    value = clean(value)
    key = norm_key(value)
    if "slot" in key:
        return "SLOTS"
    if "nextgen" in key or "casual" in key or "virtual" in key:
        return "NEXT-GEN"
    if "classic" in key or "table" in key or "dice" in key or "roulette" in key:
        return "CLASSIC"
    return value.upper()


def normalize_mechanic(*values):
    text = " ".join(clean(v) for v in values if clean(v)).upper()
    if "WINWAYS" in text or "WIN WAYS" in text or "WAYS" in text:
        return "WINWAYS"
    if "PAYLINE" in text:
        return "PAYLINES"
    if "CASCADE" in text or "CASCADING" in text:
        return "CASCADE"
    return ""


def parse_jsonish(value, default):
    if not clean(value):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def existing_icon_cache():
    icons = {}
    if not CSV_PATH.exists():
        return icons
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ident = clean(row.get("identifier"))
            icon = clean(row.get("icon"))
            if ident and icon.startswith("data:image/"):
                icons[ident] = icon
    return icons


def placeholder_image(name):
    title = clean(name) or "Game"
    initial = (title[:1] or "?").upper()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="320" viewBox="0 0 320 320">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#c9a33a"/><stop offset="1" stop-color="#05060a"/></linearGradient></defs>
<rect width="320" height="320" fill="url(#g)"/>
<text x="160" y="154" text-anchor="middle" font-family="Arial, sans-serif" font-size="82" font-weight="800" fill="#fff">{initial}</text>
<text x="160" y="204" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#f7e4a2">ART PENDING</text>
</svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def image_to_data_uri(src, name):
    src = clean(src)
    if not src:
        return None
    if src.startswith("data:image/"):
        return src
    if not src.startswith(("http://", "https://")):
        return None
    try:
        raw = urlopen(Request(src, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(image, (320, 320), method=Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, "WEBP", quality=68, method=6)
        return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    except Exception as exc:
        print(f"Image fallback used for {name}: {exc}", file=sys.stderr)
        return None


def normalize_row(row, collection):
    name = get(row, "Product Name EN", "Name", "Game Name", "Game")
    raw_identifier = get(row, "Game Identifier", "Identifier", "Slug", "Game ID")
    ident = slug(raw_identifier, name)
    if not ident:
        return None
    if not name:
        name = ident.replace("-", " ").title()

    names = {}
    for lang, col in LANG_COLUMNS.items():
        value = get(row, col, lang)
        if value:
            if value.upper() not in {"TRUE", "FALSE"}:
                names[lang] = value
    if name:
        names["EN"] = name

    languages = {}
    for lang in [k for k in LANG_COLUMNS if k != "HANT"]:
        languages[lang] = truthy(get(row, f"Language Available {lang}", lang)) or bool(names.get(lang))

    cert = {
        "UKGC": get(row, "UKGC Certification"),
        "GLI19": get(row, "GLI 19 Certification", "GLI19 Certification"),
        "PAGCOR": get(row, "PAGCOR Approved", "PAGCOR Certification"),
        "Peru": get(row, "Peru (Global Labs) Certification", "Peru Global Labs Certification", "Global Labs Certification (Peru)"),
    }
    features = {col: True for col in FEATURE_COLUMNS if truthy(get(row, col))}
    integrations = {
        "QM/AWC": get(row, "QM/AWC Integrated", "QM/AWC Production Ready Date"),
        "Hub88": get(row, "Hub88 Integrated", "Hub88 Production Ready Date"),
        "QM-SA": get(row, "QM-SA Integrated", "QM-SA Production Ready Date"),
        "IGK": get(row, "IGK Integrated", "IGK Production ReadyDate"),
    }
    integrations = {k: v for k, v in integrations.items() if v}
    sizes = {
        "Transfer MB": get(row, "TRANSFER GAME SIZE (MB)", "TRANSFER GAME SIZE （MB）"),
        "Resource MB": get(row, "RESOURCE GAME SIZE (MB)"),
    }
    sizes = {k: v for k, v in sizes.items() if v}
    assets = {
        "Brochure EN": get(row, "Brochure EN"),
        "Brochure CN": get(row, "Brochure CN"),
        "Landing": get(row, "Game Landing"),
        "Logo": get(row, "Game Logo"),
        "Banners / Assets": get(row, "Game Banners / Assets", "Game Banners", "Game Assets"),
        "PSD File": get(row, "PSD File"),
        "Promo Video": get(row, "Promo Video"),
        "GDD": get(row, "Game Design Document"),
    }
    assets = {k: v for k, v in assets.items() if v and v != "N.A"}

    return {
        "collection": collection,
        "identifier": ident,
        "name": NAME_FIXES.get(ident, name),
        "names": names,
        "studio": get(row, "Studio", "Provider") or "KM",
        "gid": get(row, "GID"),
        "exclusivity": get(row, "Exclusivity"),
        "status": normalize_status(get(row, "Status", "Stage", "State")),
        "firstLive": get(row, "First Live Date", "Initial Release Date", "First Live", "Release Date"),
        "icon": get(row, "Game Icon", "Game Icon URL", "Icon", "Image URL"),
        "logo": get(row, "Logo"),
        "rtp": get(row, "RTP"),
        "highestPayout": get(row, "Highest Payout (Single Bet)", "Highest Payout"),
        "maxWin": get(row, "Max Win (Highest payout including bonus)", "Max Win Highest payout including bonus", "Max Win"),
        "volatility": get(row, "Volatility").upper(),
        "commission": get(row, "Commission"),
        "hitRate": get(row, "Hit Rate"),
        "genre": normalize_genre(get(row, "GENRE / GAME TYPE", "Genre", "Game Type")),
        "mechanic": normalize_mechanic(get(row, "", "Line/Ways")),
        "bonus": get(row, "Bonus"),
        "tags": [tag.strip() for tag in re.split(r"[,/|]", get(row, "Tags")) if tag.strip()],
        "originated": get(row, "Game Originated", "Originated"),
        "countryDAU": get(row, "Country (DAU)", "Country DAU"),
        "themes": get(row, "Additional Info / Tags / Themes", "Additional Info / Tags", "Themes"),
        "market": get(row, "Market Filter"),
        "additionalMarket": get(row, "Additional Market Filter"),
        "countryFilter": get(row, "Country Filter"),
        "display": get(row, "Display"),
        "gameType": get(row, "Game Type"),
        "winTiers": get(row, "Win Tiers"),
        "gamification": get(row, "Gamification", "Gamification Compatibility"),
        "designTheme": get(row, "Design Theme & Features"),
        "description": get(row, "Game Description", "Description"),
        "gameFeatures": get(row, "Game Features"),
        "reels": get(row, "Reels"),
        "payways": get(row, "Pay Ways", "Payways"),
        "demo": get(row, "GAME DEMO", "Game Demo", "Demo"),
        "asiaDemo": get(row, "ASIA-DEMO"),
        "gameSetting": get(row, "Game Setting"),
        "localisation": get(row, "Localisation (Translation Progress)", "Localization"),
        "cert": cert,
        "currency": get(row, "Supported Currency", "Currency"),
        "service": get(row, "Game Service"),
        "features": features,
        "languages": languages,
        "integrations": integrations,
        "sizes": sizes,
        "assets": assets,
        "variant": "",
        "variantDesc": "",
        "image_source": get(row, "Game Icon URL", "Game Icon"),
    }


def load_source_games():
    if not any(path.exists() for path in SOURCE_FILES):
        return None
    games = {}
    for path in SOURCE_FILES:
        if not path.exists():
            continue
        collection = path.stem.replace("KingMidas Games Wiki - ", "")
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                game = normalize_row(row, collection)
                if not game:
                    continue
                ident = game["identifier"]
                prior = games.get(ident, {})
                merged = {**prior, **{k: v for k, v in game.items() if v not in ("", None, [], {})}}
                for key in ["names", "cert", "features", "languages", "integrations", "sizes", "assets"]:
                    merged[key] = {**prior.get(key, {}), **game.get(key, {})}
                games[ident] = merged
    return list(games.values())


def load_canonical_games():
    games = []
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            game = {}
            for field in FIELDNAMES:
                value = row.get(field, "")
                if field in JSON_COLUMNS:
                    game[field] = parse_jsonish(value, {} if field != "tags" else [])
                else:
                    game[field] = clean(value) or None
            games.append(game)
    return games


def attach_images(games):
    cache = existing_icon_cache()
    by_name = {game["name"]: cache.get(game["identifier"]) for game in games if cache.get(game["identifier"])}
    for game in games:
        ident = game["identifier"]
        source = game.get("image_source") or game.get("icon") or IMAGE_FALLBACKS.get(ident)
        icon = cache.get(ident) or by_name.get(game["name"])
        if not icon:
            icon = image_to_data_uri(source, game["name"])
        game["icon"] = icon or placeholder_image(game["name"])
    return games


def write_games_csv(games):
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for game in games:
            row = {}
            for field in FIELDNAMES:
                value = game.get(field)
                if field in JSON_COLUMNS:
                    row[field] = json.dumps(value or ([] if field == "tags" else {}), ensure_ascii=False, separators=(",", ":"))
                else:
                    row[field] = "" if value is None else str(value)
            writer.writerow(row)


def status_meta_from_csv():
    defs = DEFAULT_STATUS_DEFS.copy()
    if STATUS_FILE.exists():
        text = STATUS_FILE.read_text(encoding="utf-8-sig", errors="ignore")
        for line in text.splitlines():
            if "=" not in line:
                continue
            status, desc = line.split("=", 1)
            status = clean(status)
            desc = clean(desc)
            if status and desc:
                defs[status] = desc
    return {status: {"c": STATUS_COLORS.get(status, "var(--notstarted)"), "d": desc} for status, desc in defs.items()}


def update_html(games):
    html = HTML_PATH.read_text(encoding="utf-8", errors="ignore")
    games_json = json.dumps(games, ensure_ascii=False, separators=(",", ":"))
    html, count = re.subn(r"let GAMES = \[.*?\];\n", lambda _: f"let GAMES = {games_json};\n", html, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("Could not replace GAMES array")

    status_json = json.dumps(status_meta_from_csv(), ensure_ascii=False, separators=(",", ":"))
    html, status_count = re.subn(r"const STATUS_META = \{.*?\};\nconst VARIANT_META=", lambda _: f"const STATUS_META = {status_json};\nconst VARIANT_META=", html, count=1, flags=re.S)
    if status_count != 1:
        raise RuntimeError("Could not replace STATUS_META")
    HTML_PATH.write_text(html, encoding="utf-8")


def main():
    games = load_source_games()
    if games is None:
        if not CSV_PATH.exists():
            raise FileNotFoundError(f"Missing {CSV_PATH}")
        games = load_canonical_games()
    games = attach_images(games)
    write_games_csv(games)
    update_html(games)

    missing = [game["identifier"] for game in games if not game.get("icon")]
    print(f"Updated {HTML_PATH}")
    print(f"Games: {len(games)}")
    print(f"Missing icons: {len(missing)}")
    source_total = len(SOURCE_FILES) + 1
    print(f"Sources: {sum(1 for p in SOURCE_FILES + [STATUS_FILE] if p.exists())}/{source_total}")
    if missing:
        for item in missing:
            print(f"- {item}")
        sys.exit(2)


if __name__ == "__main__":
    main()
