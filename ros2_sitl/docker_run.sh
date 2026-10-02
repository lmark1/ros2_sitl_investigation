#!/bin/bash
# Start (or re-attach to) the ros2_sitl container. Same idea as
# uav_ros_simulation/run_docker.sh, different image. Runs next to the Noetic
# container and does not touch it.
#
#   ./docker_run.sh            interactive shell (creates, starts or attaches)
#   ./docker_run.sh -d         create and start detached, then ./docker_run.sh to attach
#   ./docker_run.sh --nogpu    same image without GPU, X and --privileged, container
#                              ros2_sitl_nogpu (the CI case); combine with -d
#
# ros2_ws is NOT bind mounted: the workspace built into the image is used as is.
# This folder is mounted at /root/ros2_sitl for sessions, scripts and logs.
set -e
cd "$(dirname "$0")"

NAME=ros2_sitl; DETACHED=""; GPU=true
for a in "$@"; do
  case "$a" in
    -d) DETACHED="-d";;
    --nogpu) NAME=ros2_sitl_nogpu; GPU=false;;
  esac
done

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
        exec docker exec -it "$NAME" bash
    fi
    exec docker start -ai "$NAME"
fi

# Stable name for the agent socket, the real path changes between logins.
mkdir -p ~/.ssh
ln -sf "$SSH_AUTH_SOCK" ~/.ssh/ssh_auth_sock

ARGS=(--network host
      --volume "$HOME/.ssh/ssh_auth_sock:/ssh-agent" --env SSH_AUTH_SOCK=/ssh-agent
      --volume "$(pwd):/root/ros2_sitl"
      --env GZ_VERSION=harmonic --env TERM=xterm-256color)

if $GPU; then
    # X cookie for root inside the container, same trick as run_docker.sh. Kept in a
    # user owned file: a /tmp path can be left behind unwritable by another user.
    XAUTH="$HOME/.ros2_sitl.xauth"
    touch "$XAUTH"
    xauth nlist "$DISPLAY" 2>/dev/null | sed -e 's/^..../ffff/' | xauth -f "$XAUTH" nmerge - 2>/dev/null || true
    ARGS+=(--privileged --gpus all --env NVIDIA_DRIVER_CAPABILITIES=all
           --volume /tmp/.X11-unix:/tmp/.X11-unix:rw
           --volume "$XAUTH:/tmp/.docker.xauth:rw" --env XAUTHORITY=/tmp/.docker.xauth
           --env DISPLAY="$DISPLAY")
fi

exec docker run -it $DETACHED "${ARGS[@]}" --name "$NAME" ros2_sitl:jazzy
# When detached the container idles in bash; attach with ./docker_run.sh
