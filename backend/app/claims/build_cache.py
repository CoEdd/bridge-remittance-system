"""
Build the scripted-mode cache: ask Claude once for the claims of the six bundled demo
documents and keep its answers, with the model name and the date.

Run with a key and AGENT_MODE=live:  make claims-cache
"""

import json
from datetime import datetime, timezone

from app.claims.extract import CACHE_FILE, ask_claude, text_key
from app.documents import injection
from app.documents.reader import read_message, read_pdf
from app.llm import model_name
from app.seed.demo_docs import DEMO_DOCUMENTS, demo_docs_dir


def main() -> None:
    documents = {}
    for demo in DEMO_DOCUMENTS.values():
        data = (demo_docs_dir() / demo.filename).read_bytes()
        read = read_pdf(data) if demo.filename.endswith(".pdf") else read_message(data.decode("utf-8"))
        # Claude is shown what the pipeline shows it: the text with hidden instructions blanked out.
        visible = injection.blank_out(read.text, injection.hidden_ranges(injection.detect(read.text, read.runs)))
        claims = ask_claude(visible)
        documents[text_key(visible)] = {
            "filename": demo.filename,
            "claims": [{"type": claim.type, "args": claim.args, "source": claim.source} for claim in claims],
        }
        print(f"{demo.filename}: {len(claims)} claims")
    cache = {
        "model": model_name(),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "note": "Claims returned by one live run of Claude on the bundled demo documents. Used in scripted mode.",
        "documents": documents,
    }
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {CACHE_FILE.name} ({cache['model']}, {cache['date']})")


if __name__ == "__main__":
    main()
