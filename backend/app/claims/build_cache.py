"""
Build the scripted-mode cache: ask Claude once for the claims of the six bundled demo
documents and keep its answers, with the model name and the date.

Run with a key and AGENT_MODE=live:  make claims-cache
To refresh only some documents and keep the rest:  python -m app.claims.build_cache tuition_invoice changed_details
"""

import json
import sys
from datetime import datetime, timezone

from app.claims.extract import CACHE_FILE, ask_claude, load_cache, text_key
from app.documents import injection
from app.documents.reader import read_message, read_pdf
from app.llm import model_name
from app.seed.demo_docs import DEMO_DOCUMENTS, demo_docs_dir


def main(only: list[str]) -> None:
    unknown = set(only) - set(DEMO_DOCUMENTS)
    if unknown:
        raise SystemExit(f"Unknown demo documents: {', '.join(sorted(unknown))}")
    today = datetime.now(timezone.utc).date().isoformat()
    previous = load_cache() or {}
    # Documents not being refreshed keep their entries, with the model and date of their own run.
    refreshed = {DEMO_DOCUMENTS[key].filename for key in only} if only else {demo.filename for demo in DEMO_DOCUMENTS.values()}
    documents = {
        key: {"model": entry.get("model", previous.get("model")), "date": entry.get("date", previous.get("date")), **entry}
        for key, entry in (previous.get("documents") or {}).items()
        if entry["filename"] not in refreshed
    }
    for demo in DEMO_DOCUMENTS.values():
        if demo.filename not in refreshed:
            continue
        data = (demo_docs_dir() / demo.filename).read_bytes()
        read = read_pdf(data) if demo.filename.endswith(".pdf") else read_message(data.decode("utf-8"))
        # Claude is shown what the pipeline shows it: the text with hidden instructions blanked out.
        visible = injection.blank_out(read.text, injection.hidden_ranges(injection.detect(read.text, read.runs)))
        claims = ask_claude(visible)
        documents[text_key(visible)] = {
            "filename": demo.filename,
            "model": model_name(),
            "date": today,
            "claims": [{"type": claim.type, "args": claim.args, "source": claim.source} for claim in claims],
        }
        print(f"{demo.filename}: {len(claims)} claims")
    cache = {
        "model": model_name(),
        "date": today,
        "note": "Claims returned by one live run of Claude on the bundled demo documents. Used in scripted mode.",
        "documents": documents,
    }
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {CACHE_FILE.name} ({cache['model']}, {cache['date']})")


if __name__ == "__main__":
    main(sys.argv[1:])
