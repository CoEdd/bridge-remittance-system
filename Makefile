.PHONY: up down test reset logs

# Build and start the backend (port 8000) and frontend (port 3000). Ctrl+C stops them.
up:
	docker compose up --build

# Stop and remove the containers. The SQLite volume is kept.
down:
	docker compose down

# Run the backend tests inside a freshly built backend image.
test:
	docker compose run --rm --build backend pytest

# Restore the demo: rebuild the database from the seed data and freeze fresh FX rates.
# The app must be running (make up).
reset:
	@curl -fsS -X POST http://localhost:8000/demo/reset && echo \
		|| (echo "Reset failed. Start the app first with: make up"; exit 1)

# Follow the logs of both services.
logs:
	docker compose logs -f
