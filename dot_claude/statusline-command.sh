#!/bin/bash
# Claude Code statusLine command.
# Layout: model (effort) · current_dir · current_usage · rate_limits · version · session_id

input=$(cat)

cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
model=$(echo "$input" | jq -r '.model.display_name')
effort=$(echo "$input" | jq -r '.effort.level // empty')
version=$(echo "$input" | jq -r '.version')
session_id=$(echo "$input" | jq -r '.session_id')
session_short=${session_id:0:8}

# Dimmed ANSI colors (the statusLine footer renders dimmed already)
LIGHTBLUE='\033[1;34m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
MAGENTA='\033[0;35m'
GRAY='\033[0;90m'
RESET='\033[0m'

# Trim the path to its last 4 segments, prefixed with "..." if truncated.
trimmed=$(printf '%s' "$cwd" | awk -F/ '{
  n = NF
  if (n > 4) {
    out = "..."
    for (i = n - 3; i <= n; i++) out = out "/" $i
  } else {
    out = $0
  }
  print out
}')

model_field="$model"
[ -n "$effort" ] && model_field="$model_field ($effort)"

used_pct=$(echo "$input" | jq -r '
  .context_window as $c
  | if $c == null then empty
    elif $c.used_percentage != null then $c.used_percentage
    elif $c.current_usage != null and ($c.context_window_size // 0) > 0 then
      (($c.current_usage.input_tokens // 0) + ($c.current_usage.cache_creation_input_tokens // 0) + ($c.current_usage.cache_read_input_tokens // 0)) * 100 / $c.context_window_size
    else empty end')
usage_field=""
win=$(echo "$input" | jq -r '.context_window.context_window_size // empty')
win_field=""
[ -n "$win" ] && win_field=$(awk -v w="$win" 'BEGIN{ if (w>=1000) printf "/%dk", w/1000; else printf "/%d", w }')
[ -n "$used_pct" ] && usage_field=$(printf 'ctx %.0f%%%s' "$used_pct" "$win_field")

five=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
week=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
spend=$(echo "$input" | jq -r '.rate_limits.spend_limit.used_percentage // empty')
rate_field=""
[ -n "$five" ] && rate_field="5h $(awk -v v="$five" 'BEGIN{printf "%.0f", 100-v}')% left"
if [ -n "$week" ]; then
  [ -n "$rate_field" ] && rate_field="$rate_field "
  rate_field="${rate_field}7d $(awk -v v="$week" 'BEGIN{printf "%.0f", 100-v}')% left"
fi
if [ -n "$spend" ]; then
  [ -n "$rate_field" ] && rate_field="$rate_field "
  rate_field="${rate_field}spend $(awk -v v="$spend" 'BEGIN{printf "%.0f", 100-v}')% left"
fi

SEP=" ${GRAY}\xc2\xb7${RESET} "

out="${LIGHTBLUE}${model_field}${RESET}${SEP}${CYAN}${trimmed}${RESET}"
[ -n "$usage_field" ] && out="${out}${SEP}${YELLOW}${usage_field}${RESET}"
[ -n "$rate_field" ] && out="${out}${SEP}${MAGENTA}${rate_field}${RESET}"
out="${out}${SEP}${GRAY}v${version}${RESET}${SEP}${GRAY}${session_short}${RESET}"

printf '%b\n' "$out"
