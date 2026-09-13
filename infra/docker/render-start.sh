#!/bin/sh
# Render's "Docker Command" field doesn't reliably parse shell chaining
# (&&, nested quotes) passed as a single string — a plain script path
# sidesteps whatever it does internally, since there's nothing left for it
# to mis-tokenize. Used as this service's dockerCommand in render.yaml,
# in place of Render's unsupported (free-plan) preDeployCommand.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
