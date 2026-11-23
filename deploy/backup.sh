#!/bin/sh
set -eu
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 MODEL_DIRECTORY AGE_RECIPIENT OUTPUT.age" >&2
    exit 2
fi
model_dir=$(realpath "$1")
recipient=$2
output=$3
test -f "$model_dir/manifest.json"
test ! -e "$output"
umask 077
work=$(mktemp -d)
encrypted=$(mktemp "$(dirname "$output")/.welding-encrypted.XXXXXX")
restart=false
cleanup() {
    status=$?
    trap - EXIT
    rm -rf -- "$work"
    rm -f -- "$encrypted"
    if [ "$restart" = true ]; then
        docker compose up -d --wait api proxy || status=1
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
docker compose ps --status running --services | grep -qx api && restart=true
docker compose stop proxy api
docker compose exec -T postgres pg_dump -U postgres -d welding --format=custom > "$work/welding.dump"
docker compose run --rm --no-deps -T api tar -C /opt/welding/runtime/exports -cf - . > "$work/exports.tar"
tar -C "$model_dir" -cf "$work/model.tar" .
docker compose config --images > "$work/images.txt"
tar -C "$work" -cf "$work/payload.tar" welding.dump exports.tar model.tar images.txt
age -r "$recipient" "$work/payload.tar" > "$encrypted"
ln "$encrypted" "$output"
