#!/bin/sh
# Render's "Docker Command" field doesn't reliably parse shell chaining
# (&&, nested quotes) passed as a single string — a plain script path
# sidesteps whatever it does internally, since there's nothing left for it
# to mis-tokenize. Used as this service's dockerCommand in render.yaml,
# in place of Render's unsupported (free-plan) preDeployCommand.
set -e
alembic upgrade head

# No separate celery worker process here. Render's free web-service tier
# has no free background-worker instance type at all (confirmed: the
# Blueprint silently failed to create hybridrag-celery-worker — background
# workers are paid-plan only), and running a worker alongside uvicorn in
# this same container was tried and verified OOM-killed on the very first
# real upload — each process loads its own separate copy of the embedding
# model, and together they exceed the free tier's 512MB. Instead,
# CELERY_TASK_ALWAYS_EAGER=true (see app/core/config.py) makes document
# processing run in-process, in the same request that uploaded it — one
# process, one model copy, no worker needed.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
