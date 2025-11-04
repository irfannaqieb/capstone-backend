import os
import pandas as pd
import uuid
from urllib.parse import urljoin
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
assert DATABASE_URL, "DATABASE_URL environment variable not set"

BASE_URL = os.getenv("R2_URL")
assert BASE_URL, "R2_URL environment variable not set"

DATASETS = {
    "gpt5": {
        "folder": "dataset/dataset_gpt",
        "name": lambda i: f"gpt_{i:02d}",
    },
    "gemini25": {
        "folder": "dataset/dataset_gemini",
        "name": lambda i: f"gemini_{i:02d}",
    },
    "flux1_dev": {
        "folder": "dataset/dataset_flux1_dev",
        "name": lambda i: f"dev_{i:02d}",
    },
    "flux1_krea": {
        "folder": "dataset/dataset_flux1_krea",
        "name": lambda i: f"krea_{i:02d}",
    },
    "kolors": {
        "folder": "dataset/dataset_kolors",
        "name": lambda i: f"kolors_{i:02d}",
    },
}

PROMPT_COUNT = 300


def load_prompts_xlsx(path: str) -> dict[str, str]:
    """
    Loads your prompts.xlsx and returns a mapping like:
    {'1': 'An image of a batman having pizza in the city in anime style.', ...}
    """
    df = pd.read_excel(path)

    # Pick the 'Natural sentence' column
    text_col = None
    for c in df.columns:
        if "natural" in str(c).lower():
            text_col = c
            break
    if text_col is None:
        raise ValueError("Couldn't find a column named 'Natural sentence' in Excel!")

    d = {}
    for idx, row in df.iterrows():
        pid = str(idx + 1)  # row2 -> id '1'
        text_val = str(row[text_col]).strip()
        d[pid] = text_val

    # Optional: sanity check
    if len(d) != PROMPT_COUNT:
        print(
            f"Loaded {len(d)} prompts from Excel but PROMPT_COUNT={PROMPT_COUNT}. Proceeding anyway."
        )

    return d


def build_url(folder: str, stem: str) -> str:
    base = BASE_URL if BASE_URL.endswith("/") else BASE_URL + "/"
    rel = f"{folder.rstrip('/')}/{stem}.png"
    return urljoin(base, rel)


def upsert_prompt(conn, prompt_id: str, text_val: str = ""):
    conn.execute(
        text(
            """
        INSERT INTO prompts (id, text) 
        VALUES (:pid, :text)
        ON CONFLICT (id) 
        DO UPDATE SET text = EXCLUDED.text
    """
        ),
        {"pid": prompt_id, "text": text_val},
    )


def upsert_image(conn, prompt_id: str, model: str, url: str):
    conn.execute(
        text(
            """
        INSERT INTO images (id, prompt_id, model, url)
        VALUES (gen_random_uuid(), :pid, :model, :url)
        ON CONFLICT (prompt_id, model)
        DO UPDATE SET url = EXCLUDED.url
    """
        ),
        {"pid": prompt_id, "model": model, "url": url},
    )


def main():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable not set")

    print("=" * 60)
    print("Starting data ingestion...")
    print(f"Database: {DATABASE_URL[:50]}...")
    print(f"R2 Base URL: {BASE_URL}")
    print(f"Target: {PROMPT_COUNT} prompts")
    print("=" * 60)

    engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

    # Load prompts
    print("\n📖 Loading prompts from prompts.xlsx...")
    try:
        prompts_map = load_prompts_xlsx("prompts.xlsx")
        print(f"✅ Loaded {len(prompts_map)} prompts from Excel")
    except Exception as e:
        raise SystemExit(f"❌ Error loading prompts.xlsx: {e}")

    print("\n🔄 Starting database insertion...\n")

    with engine.begin() as conn:
        for i in range(1, PROMPT_COUNT + 1):
            pid = str(i)
            text_val = prompts_map.get(pid, "")

            # Show progress every 10 items
            if i % 10 == 0:
                print(f"⏳ Processing prompt {i}/{PROMPT_COUNT}...")
            elif i == 1:
                print(f"⏳ Processing prompt {i}/{PROMPT_COUNT}...")

            # prompt
            upsert_prompt(conn, pid, text_val)

            # images for all 5 models
            for model, cfg in DATASETS.items():
                folder = cfg["folder"]
                stem = cfg["name"](i)
                url = build_url(folder, stem)
                upsert_image(conn, pid, model, url)

    print("\n" + "=" * 60)
    print(f"✅ Ingestion complete!")
    print(f"   - {PROMPT_COUNT} prompts inserted")
    print(f"   - {PROMPT_COUNT * 5} images inserted (5 models per prompt)")
    print(f"   - Models: gpt5, gemini25, flux1_dev, flux1_krea, kolors")
    print("=" * 60)


if __name__ == "__main__":
    main()
