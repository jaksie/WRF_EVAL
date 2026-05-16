from pathlib import Path
from urllib.parse import urljoin
import re, requests, zipfile

BASE_URL = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/terminowe/synop/2026/"

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_DIR / "input" / "imgw" / "raw"

OUT_DIR.mkdir(parents=True, exist_ok=True)

html = requests.get(BASE_URL).text
files = re.findall(r'href="([^"]+\.zip)"', html)

for file in files:
    zip_url = urljoin(BASE_URL, file)
    zip_path = OUT_DIR / file

    print(file)
    zip_path.write_bytes(requests.get(zip_url).content)

    with zipfile.ZipFile(zip_path) as z:
        z.extractall(OUT_DIR)

        zip_path.unlink() 