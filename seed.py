"""
Run once after setting up Supabase to populate seeded documents.

  python seed.py
"""
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from ingest import save_document  # noqa: E402

SEEDED_DIR = Path(__file__).parent / "docs" / "seeded"


def seed():
    files = sorted(SEEDED_DIR.glob("*.txt"))
    if not files:
        print("No seeded docs found in docs/seeded/")
        return

    for path in files:
        title = path.stem.replace("_", " ").title()
        content = path.read_text(encoding="utf-8")
        entry = save_document(title=title, content=content, origin="seeded", filename=path.name)
        print(f"  Seeded: {entry['title']} ({entry['id']})")

    print(f"\nDone. {len(files)} document(s) seeded.")


if __name__ == "__main__":
    seed()
