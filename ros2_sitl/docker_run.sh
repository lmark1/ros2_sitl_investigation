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
DETACHED=""
if [ "$1" == "-d" ]; then DETACHED="-d"; shift; fi

# Stable name for the agent socket, the real path changes between logins.
mkdir -p ~/.ssh
ln -sf "$SSH_AUTH_SOCK" ~/.ssh/ssh_auth_sock

# X cookie for the root user inside, same trick as uav_ros_simulation/run_docker.sh.
XSOCK=/tmp/.X11-unix
XAUTH=/tmp/.docker.xauth
touch $XAUTH
xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | xauth -f $XAUTH nmerge - 2>/dev/null || true

if docker ps -a --format '{{.Names}}' | grep -qx ros2_sitl; then
    if docker ps --format '{{.Names}}' | grep -qx ros2_sitl; then
        exec docker exec -it ros2_sitl bash
    fi
    exec docker start -ai ros2_sitl
fi

exec docker run -it $DETACHED --network host --privileged \
  --gpus all --env NVIDIA_DRIVER_CAPABILITIES=all \
  --volume ~/.ssh/ssh_auth_sock:/ssh-agent --env SSH_AUTH_SOCK=/ssh-agent \
  --volume $XSOCK:$XSOCK:rw --volume $XAUTH:$XAUTH:rw \
  --env XAUTHORITY=$XAUTH --env DISPLAY="$DISPLAY" --env TERM=xterm-256color \
  --volume "$(pwd):/root/ros2_sitl" \
  --env GZ_VERSION=harmonic \
  --name ros2_sitl ros2_sitl:jazzy "$@"
# When detached the container idles in bash; attach with ./docker_run.sh
