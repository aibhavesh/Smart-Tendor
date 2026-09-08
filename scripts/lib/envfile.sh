# shellcheck shell=bash
# Shared dotenv helpers for scripts/setup.sh and scripts/dev.sh.
# Source it:  . "$(dirname "$0")/lib/envfile.sh"

# Values a template ships as "not filled in yet". set_env_value --keep
# overwrites these but never a real answer, which is what makes re-running
# setup safe.
_is_placeholder() {
    case "$1" in
        "" | "change-me-in-production") return 0 ;;
        *) return 1 ;;
    esac
}

if [ -t 1 ]; then
    _C_STEP=$'\033[36m'; _C_OK=$'\033[32m'; _C_WARN=$'\033[33m'
    _C_DIM=$'\033[90m'; _C_OFF=$'\033[0m'
else
    _C_STEP=""; _C_OK=""; _C_WARN=""; _C_DIM=""; _C_OFF=""
fi

# Set by the calling script so messages can name files relative to the repo.
REPO_ROOT="${REPO_ROOT:-}"
show_path() {
    if [ -n "$REPO_ROOT" ]; then
        printf '%s' "${1#"$REPO_ROOT"/}"
    else
        printf '%s' "$1"
    fi
}

step() { printf '%s==> %s%s\n' "$_C_STEP" "$*" "$_C_OFF"; }
note() { printf '%s    %s%s\n' "$_C_DIM" "$*" "$_C_OFF"; }
ok()   { printf '%s    %s%s\n' "$_C_OK" "$*" "$_C_OFF"; }
warn() { printf '%s    %s%s\n' "$_C_WARN" "$*" "$_C_OFF"; }
die()  { printf '%s\nerror: %s%s\n' "$_C_WARN" "$*" "$_C_OFF" >&2; exit 1; }

# get_env_value <file> <KEY> -> prints the value, empty when absent.
get_env_value() {
    local file="$1" key="$2"
    [ -f "$file" ] || return 0
    sed -n -E "s/^[[:space:]]*${key}[[:space:]]*=(.*)$/\1/p" "$file" | head -n 1
}

# set_env_value <file> <KEY> <value> [--keep]
# Rewrites the KEY= line in place when it exists, appends it otherwise.
# --keep skips the write when the key already holds a non-placeholder value.
set_env_value() {
    local file="$1" key="$2" value="$3" keep="${4:-}"
    local current
    current="$(get_env_value "$file" "$key")"

    if [ "$keep" = "--keep" ] && [ -n "$current" ] && ! _is_placeholder "$current"; then
        return 0
    fi

    [ -f "$file" ] || : > "$file"

    if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$file"; then
        # awk rather than sed -i: portable across GNU and BSD, and it never
        # reinterprets the replacement text (secrets contain / and & freely).
        local tmp
        tmp="$(mktemp)"
        KEY="$key" VALUE="$value" awk '
            BEGIN { done = 0 }
            !done && $0 ~ "^[[:space:]]*" ENVIRON["KEY"] "[[:space:]]*=" {
                print ENVIRON["KEY"] "=" ENVIRON["VALUE"]; done = 1; next
            }
            { print }
        ' "$file" > "$tmp"
        mv "$tmp" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

# copy_env_template <template> <destination>
copy_env_template() {
    local template="$1" destination="$2"
    if [ -f "$destination" ]; then
        note "$(show_path "$destination") already exists — keeping it."
        return 0
    fi
    [ -f "$template" ] || die "Missing template $(show_path "$template"). Is this a complete clone of the repository?"
    cp "$template" "$destination"
    ok "Created $(show_path "$destination") from $(show_path "$template")"
}

# 48 random bytes, URL-safe base64 — the value .env.backend.example tells you to
# generate. Falls back through openssl, python3, then /dev/urandom.
new_jwt_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 48 | tr '+/' '-_' | tr -d '=\n'
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
    else
        head -c 48 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'
    fi
}

# read_required <prompt> <ENV_FALLBACK> <non_interactive:0|1> [validator_fn] [validation_message]
# Prints the answer on stdout; prompts go to stderr so command substitution works.
read_required() {
    local prompt="$1" envname="$2" noninteractive="$3"
    local validator="${4:-}" message="${5:-That value does not look right.}"
    local preset answer

    preset="$(eval "printf '%s' \"\${$envname:-}\"")"
    if [ -n "$preset" ]; then
        if [ -n "$validator" ] && ! "$validator" "$preset"; then
            die "$envname is set but invalid. $message"
        fi
        note "$envname supplied from the environment." >&2
        printf '%s' "$preset"
        return 0
    fi

    if [ "$noninteractive" = "1" ]; then
        die "$envname is required in --non-interactive mode but is not set."
    fi

    while true; do
        printf '%s' "$prompt" >&2
        IFS= read -r answer || die "No input available. Re-run with --non-interactive and set $envname."
        answer="$(printf '%s' "$answer" | tr -d '[:space:]')"
        if [ -z "$answer" ]; then
            warn "This value is required." >&2
            continue
        fi
        if [ -n "$validator" ] && ! "$validator" "$answer"; then
            warn "$message" >&2
            continue
        fi
        printf '%s' "$answer"
        return 0
    done
}

# read_optional <prompt> <ENV_FALLBACK> <non_interactive:0|1>
read_optional() {
    local prompt="$1" envname="$2" noninteractive="$3" preset answer
    preset="$(eval "printf '%s' \"\${$envname:-}\"")"
    if [ -n "$preset" ]; then printf '%s' "$preset"; return 0; fi
    if [ "$noninteractive" = "1" ]; then return 0; fi
    printf '%s' "$prompt" >&2
    IFS= read -r answer || return 0
    printf '%s' "$(printf '%s' "$answer" | tr -d '[:space:]')"
}

# wait_postgres_healthy [timeout_seconds]
# Resolves the container through `docker compose ps -q`, so it does not depend
# on the generated container name.
wait_postgres_healthy() {
    local timeout="${1:-120}" waited=0 id state
    while :; do
        id="$(docker compose ps -q postgres 2>/dev/null | head -n 1)"
        if [ -n "$id" ]; then
            state="$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || true)"
            # Explicit ifs, not `[ ... ] && ...`: a false test would make the
            # whole && list return non-zero and `set -e` would abort the script.
            if [ "$state" = "healthy" ]; then return 0; fi
            if [ "$state" = "unhealthy" ]; then
                die "The postgres container reports unhealthy. Check 'docker compose logs postgres'."
            fi
        fi
        if [ "$waited" -ge "$timeout" ]; then
            die "Postgres did not become healthy within ${timeout}s. Check 'docker compose logs postgres'."
        fi
        sleep 2
        waited=$((waited + 2))
    done
}
