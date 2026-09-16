#!/bin/bash
# Start (or re-attach to) the ros2_sitl container. Same flags as
# uav_ros_simulation/run_docker.sh, different image. Runs next to the Noetic
# container, does not touch it.
#
# ros2_ws is NOT bind mounted: the workspace built into the image is used as is,
# so that what runs is exactly what the Dockerfile produced. This folder is
# mounted at /root/ros2_sitl for scripts and logs.
# Usage: ./docker_run.sh        interactive shell (creates, starts or attaches)
#        ./docker_run.sh -d     create and start detached, then use ./docker_run.sh to attach
set -e
cd "$(dirname "$0")"
#        ./docker_run.sh --nogpu [-d]   same image without GPU and X, named ros2_sitl_nogpu (CI case)
PRIV="--privileged"; DETACHED=""; NAME=ros2_sitl; GPU_ARGS="--gpus all --env NVIDIA_DRIVER_CAPABILITIES=all"
X_ARGS='--volume /tmp/.X11-unix:/tmp/.X11-unix:rw --volume /tmp/.docker.xauth:/tmp/.docker.xauth:rw --env XAUTHORITY=/tmp/.docker.xauth'
for a in "$@"; do
  case "$a" in
    -d) DETACHED="-d";;
    --nogpu) NAME=ros2_sitl_nogpu; GPU_ARGS=""; X_ARGS=""; PRIV="";;
  esac
done

# Stable name for the agent socket, the real path changes between logins.
mkdir -p ~/.ssh
ln -sf "$SSH_AUTH_SOCK" ~/.ssh/ssh_auth_sock

# X cookie for the root user inside, same trick as uav_ros_simulation/run_docker.sh.
XSOCK=/tmp/.X11-unix
XAUTH=/tmp/.docker.xauth
touch $XAUTH
xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | xauth -f $XAUTH nmerge - 2>/dev/null || true

if docker ps -a --format '{{.Names}}' | grep -qx $NAME; then
    if docker ps --format '{{.Names}}' | grep -qx $NAME; then
        exec docker exec -it $NAME bash
    fi
    exec docker start -ai $NAME
fi

# shellcheck disable=SC2086
exec docker run -it $DETACHED --network host $PRIV \
  $GPU_ARGS $X_ARGS \
  --volume ~/.ssh/ssh_auth_sock:/ssh-agent --env SSH_AUTH_SOCK=/ssh-agent \
  --env DISPLAY="$DISPLAY" --env TERM=xterm-256color \
  --volume "$(pwd):/root/ros2_sitl" \
  --env GZ_VERSION=harmonic \
  --name $NAME ros2_sitl:jazzy
# When detached the container idles in bash; attach with ./docker_run.sh
