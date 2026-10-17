.PHONY: up down test reset logs demo-docs claims-cache eval-claims e2e check-ui demo-video demo-subtitles evidence

# Build and start the backend (port 8000) and frontend (port 3000). Ctrl+C stops them.
up:
	docker compose up --build

# Stop and remove the containers. The SQLite volume is kept.
down:
	docker compose down

# Run the backend tests inside a freshly built backend image. docs/ is shared with the
# container so the tests can write docs/extraction-accuracy.json.
test:
	docker compose run --rm --build -v "$(CURDIR)/docs:/app/docs" backend pytest

# Rebuild the bundled demo documents in demo-docs/. Needs the Chinese font that the
# backend image contains. The output is the same on every run.
demo-docs:
	docker compose run --rm --build -v "$(CURDIR)/demo-docs:/app/demo-docs" backend python -m app.seed.make_demo_docs

# Restore the demo: rebuild the database from the seed data and freeze fresh FX rates.
# The app must be running (make up).
reset:
	@curl -fsS -X POST http://localhost:8000/demo/reset && echo \
		|| (echo "Reset failed. Start the app first with: make up"; exit 1)

# Follow the logs of both services.
logs:
	docker compose logs -f

# Ask Claude once for the claims of the six demo documents and keep the answers, so that
# scripted mode can show the claim check offline. Needs ANTHROPIC_API_KEY in .env.
claims-cache:
	docker compose run --rm --build -v "$(CURDIR)/backend/app/claims/cache:/app/app/claims/cache" backend python -m app.claims.build_cache

# Measure the claim check on the test split (live mode only): keyword rules, claim check,
# and both. Writes docs/claim-check-eval.md and backend/eval/claims/results.json.
eval-claims:
	docker compose run --rm --build -v "$(CURDIR)/docs:/app/docs" -v "$(CURDIR)/backend/eval:/app/eval" backend python -m eval.claims.run

# The end-to-end test of the whole demo (Playwright, frontend/e2e/demo.spec.ts). Starts the
# app in scripted mode, runs the test with the Chrome on this machine, then starts the app
# again with the settings in .env. Needs Node on the host: cd frontend && npm install.
e2e:
	docker compose -f docker-compose.yml -f docker-compose.scripted.yml up -d --build
	@until curl -fs http://localhost:8000/health | grep -q '"agent_mode":"scripted"'; do sleep 1; done
	@until curl -fs -o /dev/null http://localhost:3000/; do sleep 1; done
	cd frontend && npx playwright test; status=$$?; cd .. && mkdir -p frontend/test-results \
		&& docker compose logs --no-color backend > frontend/test-results/backend.log; docker compose up -d; exit $$status

# The frontend's design rules and colour contrast (no Docker needed).
check-ui:
	cd frontend && npm run check:design && npm run check:contrast

# Record the demo video (scripts/video/record_demo.ts): evidence/video/bridge-demo-clean.mp4
# and scripts/video/timeline.json, then the subtitles (scripts/video/subtitles.ts). MODE=scripted (the default) needs no API key; MODE=live
# uses the settings in .env and needs ANTHROPIC_API_KEY. Starts the app in that mode, records
# with the Chrome on this machine, then starts the app again with the settings in .env.
# Needs Node 22.18+ (cd frontend && npm install), ffmpeg and poppler (brew install ffmpeg poppler).
MODE ?= scripted
demo-video:
	@if [ "$(MODE)" = "live" ]; then docker compose up -d --build; \
		else docker compose -f docker-compose.yml -f docker-compose.scripted.yml up -d --build; fi
	@for i in $$(seq 120); do curl -fs http://localhost:8000/health | grep -q '"agent_mode":"$(MODE)"' && break; sleep 1; done; \
		curl -fs http://localhost:8000/health | grep -q '"agent_mode":"$(MODE)"' \
		|| { echo "The backend is not in $(MODE) mode (for live, set AGENT_MODE=live and ANTHROPIC_API_KEY in .env)."; exit 1; }
	@until curl -fs -o /dev/null http://localhost:3000/; do sleep 1; done
	node scripts/video/record_demo.ts && node scripts/video/subtitles.ts; status=$$?; docker compose up -d; exit $$status

# Only the subtitles, from scripts/video/timeline.json and the clean video: bridge-demo.srt,
# bridge-demo-subtitled.mp4 and voiceover-script.md in evidence/video/. The app must be running.
demo-subtitles:
	node scripts/video/subtitles.ts

# Sandbox operation logs (scripts/evidence/sandbox_run.py): one full demo run through the API,
# from a reset, with every log in evidence/sandbox-run/. MODE as for demo-video. Needs python3.
evidence:
	@if [ "$(MODE)" = "live" ]; then docker compose up -d --build; \
		else docker compose -f docker-compose.yml -f docker-compose.scripted.yml up -d --build; fi
	@for i in $$(seq 120); do curl -fs http://localhost:8000/health | grep -q '"agent_mode":"$(MODE)"' && break; sleep 1; done; \
		curl -fs http://localhost:8000/health | grep -q '"agent_mode":"$(MODE)"' \
		|| { echo "The backend is not in $(MODE) mode (for live, set AGENT_MODE=live and ANTHROPIC_API_KEY in .env)."; exit 1; }
	python3 scripts/evidence/sandbox_run.py; status=$$?; docker compose up -d; exit $$status
