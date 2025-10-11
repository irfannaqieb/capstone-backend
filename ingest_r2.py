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
        "name": lambda i: f"gpt_{i}",
    },
    "gemini25": {
        "folder": "dataset/dataset_gemini",
        "name": lambda i: f"gemini_{i}",
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


def ensure_pair(conn, prompt_id: str, model_a: str, model_b: str):
    """
    Upsert a pair row that references the concrete image rows for (prompt_id, model_a) and (prompt_id, model_b).
    Requires a UNIQUE constraint on (prompt_id) => uq_pairs_prompt.
    """
    conn.execute(
        text(
            """
            INSERT INTO pairs (prompt_id, image_a_id, image_b_id)
            VALUES (
                :pid,
                (SELECT id FROM images WHERE prompt_id = :pid AND model = :ma LIMIT 1),
                (SELECT id FROM images WHERE prompt_id = :pid AND model = :mb LIMIT 1)
            )
            ON CONFLICT (prompt_id)
            DO UPDATE SET
                image_a_id = EXCLUDED.image_a_id,
                image_b_id = EXCLUDED.image_b_id
        """
        ),
        {"pid": prompt_id, "ma": model_a, "mb": model_b},
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

            # images (gpt & gemini)
            for model, cfg in DATASETS.items():
                folder = cfg["folder"]
                stem = cfg["name"](i)
                url = build_url(folder, stem)
                upsert_image(conn, pid, model, url)

            # create a pair entry (gpt5 vs gemini25)
            ensure_pair(conn, pid, "gpt5", "gemini25")

    print("\n" + "=" * 60)
    print(f"✅ Ingestion complete!")
    print(f"   - {PROMPT_COUNT} prompts inserted")
    print(f"   - {PROMPT_COUNT * 2} images inserted (GPT-5 + Gemini-2.5)")
    print(f"   - {PROMPT_COUNT} pairs created")
    print("=" * 60)


if __name__ == "__main__":
    main()
