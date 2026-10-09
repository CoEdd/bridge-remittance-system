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

# Placeholder: the one-click demo reset is built in a later step.
reset:
	@echo "make reset does nothing yet. The demo reset is built in a later step."

# Follow the logs of both services.
logs:
	docker compose logs -f
