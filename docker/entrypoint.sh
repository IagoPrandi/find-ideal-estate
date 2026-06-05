#!/bin/bash
set -euo pipefail

DISPLAY_VALUE="${DISPLAY:-:99}"
XVFB_PID=""
CHILD_PID=""

cleanup() {
	if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
		kill -TERM "$CHILD_PID" 2>/dev/null || true
		wait "$CHILD_PID" 2>/dev/null || true
	fi
	if [[ -n "$XVFB_PID" ]] && kill -0 "$XVFB_PID" 2>/dev/null; then
		kill -TERM "$XVFB_PID" 2>/dev/null || true
		wait "$XVFB_PID" 2>/dev/null || true
	fi
}

forward_signal() {
	local signal="$1"
	if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
		kill -"$signal" "$CHILD_PID" 2>/dev/null || true
	fi
}

start_xvfb() {
	local display_number="${DISPLAY_VALUE#:}"
	local lock_file="/tmp/.X${display_number}-lock"
	local socket_file="/tmp/.X11-unix/X${display_number}"

	if [[ -f "$lock_file" ]]; then
		local lock_pid=""
		lock_pid="$(cat "$lock_file" 2>/dev/null || true)"
		if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
			export DISPLAY="$DISPLAY_VALUE"
			return 0
		fi
		rm -f "$lock_file" "$socket_file"
	fi

	Xvfb "$DISPLAY_VALUE" -screen 0 1280x800x24 -ac &
	XVFB_PID="$!"

	for _ in $(seq 1 50); do
		if ! kill -0 "$XVFB_PID" 2>/dev/null; then
			wait "$XVFB_PID"
		fi
		if [[ -S "$socket_file" ]]; then
			export DISPLAY="$DISPLAY_VALUE"
			return 0
		fi
		sleep 0.1
	done

	echo "Xvfb did not become ready on display $DISPLAY_VALUE" >&2
	return 1
}

run_migrations() {
	local max_attempts="${MIGRATION_MAX_ATTEMPTS:-30}"
	local sleep_seconds="${MIGRATION_RETRY_SECONDS:-2}"
	local attempt=1

	while true; do
		if alembic upgrade head; then
			return 0
		fi

		if [[ "$attempt" -ge "$max_attempts" ]]; then
			echo "alembic upgrade head failed after ${attempt} attempts" >&2
			return 1
		fi

		echo "alembic upgrade head failed; retrying in ${sleep_seconds}s (${attempt}/${max_attempts})" >&2
		attempt=$((attempt + 1))
		sleep "$sleep_seconds"
	done
}

trap cleanup EXIT
trap 'forward_signal TERM' TERM
trap 'forward_signal INT' INT

start_xvfb

run_migrations

"$@" &
CHILD_PID="$!"

set +e
wait "$CHILD_PID"
EXIT_CODE="$?"
set -e

exit "$EXIT_CODE"
