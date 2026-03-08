#!/bin/bash
USER_ID=$(id -u)
GROUP_ID=$(id -g)
USER_NAME=$USER

podman run -it --rm \
    --userns=keep-id \
    --network=host \
    --user "$USER_ID:$GROUP_ID" \
    -v "$(pwd)":/workspace \
    -v "$HOME/.claude":"/home/$USER_NAME/.claude" \
    -v "$HOME/.claude.json":"/home/$USER_NAME/.claude.json" \
    -e ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
    -e ANTHROPIC_AUTH_TOKEN="$ANTHROPIC_AUTH_TOKEN" \
    -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -e LANG="$LANG" \
    -e LC_ALL="$LC_ALL" \
    -e http_proxy="$http_proxy" \
    -e https_proxy="$https_proxy" \
    -e HTTP_PROXY="$HTTP_PROXY" \
    -e HTTPS_PROXY="$HTTPS_PROXY" \
    -e NO_PROXY="$NO_PROXY" \
    -e no_proxy="$no_proxy" \
    -e TERM=xterm-256color \
    -e HOME="/home/$USER_NAME" \
    -w /workspace \
    --entrypoint sh \
    localhost/claude-code:latest \
    -c "claude --dangerously-skip-permissions \"$@\"" -- "$@"
