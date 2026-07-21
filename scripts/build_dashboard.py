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
CSV_PATH = ROOT / "data" / "games.csv"
HTML_PATH = ROOT / "index.html"

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

JSONISH_COLUMNS = {
    "cert",
    "countryDAU",
    "currency",
    "features",
    "gameFeatures",
    "languages",
    "localisation",
    "market",
    "names",
    "tags",
    "themes",
}


def parse_cell(column, value):
    value = (value or "").strip()
    if not value:
        return None
    if column in JSONISH_COLUMNS:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [part.strip() for part in value.split("|") if part.strip()]
    return value


def image_to_data_uri(src):
    if not src:
        return None
    if src.startswith("data:image/"):
        return src
    if not src.startswith(("http://", "https://")):
        return src

    req = Request(src, headers={"User-Agent": "Mozilla/5.0"})
    raw = urlopen(req, timeout=30).read()
    image = Image.open(io.BytesIO(raw))
    image = ImageOps.exif_transpose(image).convert("RGB")
    image = ImageOps.fit(
        image,
        (320, 320),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    out = io.BytesIO()
    image.save(out, "WEBP", quality=68, method=6)
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def load_games():
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        games = []
        for row in reader:
            game = {}
            for column, value in row.items():
                if column == "image_source":
                    continue
                game[column] = parse_cell(column, value)

            ident = game.get("identifier")
            if ident in NAME_FIXES:
                game["name"] = NAME_FIXES[ident]

            image_source = (
                (row.get("image_source") or "").strip()
                or (row.get("icon") or "").strip()
                or IMAGE_FALLBACKS.get(ident)
            )
            game["icon"] = image_to_data_uri(image_source)
            games.append(game)
        return games


def update_html(games):
    html = HTML_PATH.read_text(encoding="utf-8", errors="ignore")
    replacement = json.dumps(games, ensure_ascii=False, separators=(",", ":"))
    pattern = re.compile(r"let GAMES = \[.*?\];\n", flags=re.S)
    html, count = pattern.subn(lambda _: f"let GAMES = {replacement};\n", html, count=1)
    if count != 1:
        raise RuntimeError("Could not replace the GAMES array in index.html")
    HTML_PATH.write_text(html, encoding="utf-8")


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Missing {CSV_PATH}")
    if not HTML_PATH.exists():
        raise FileNotFoundError(f"Missing {HTML_PATH}")

    games = load_games()
    missing = [game.get("identifier") or game.get("name") for game in games if not game.get("icon")]
    update_html(games)

    print(f"Updated {HTML_PATH}")
    print(f"Games: {len(games)}")
    print(f"Missing icons: {len(missing)}")
    if missing:
        print("Missing icon entries:")
        for item in missing:
            print(f"- {item}")
        sys.exit(2)


if __name__ == "__main__":
    main()
