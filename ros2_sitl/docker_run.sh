#!/bin/bash
# Start (or re-attach to) the ros2_sitl container. Same flags as
# uav_ros_simulation/run_docker.sh, different image. Runs next to the Noetic
# container, does not touch it.
#
# ros2_ws is NOT bind mounted: the workspace built into the image is used as is,
# so that what runs is exactly what the Dockerfile produced. This folder is
# mounted at /root/ros2_sitl for scripts and logs.
set -e
cd "$(dirname "$0")"

# Stable name for the agent socket, the real path changes between logins.
mkdir -p ~/.ssh
ln -sf "$SSH_AUTH_SOCK" ~/.ssh/ssh_auth_sock

if docker ps -a --format '{{.Names}}' | grep -qx ros2_sitl; then
    if docker ps --format '{{.Names}}' | grep -qx ros2_sitl; then
        exec docker exec -it ros2_sitl bash
    fi
    exec docker start -ai ros2_sitl
fi

exec docker run -it --network host --privileged \
  --gpus all --env NVIDIA_DRIVER_CAPABILITIES=all \
  --volume ~/.ssh/ssh_auth_sock:/ssh-agent --env SSH_AUTH_SOCK=/ssh-agent \
  --volume /tmp/.X11-unix:/tmp/.X11-unix:rw --env DISPLAY="$DISPLAY" \
  --volume "$(pwd):/root/ros2_sitl" \
  --env GZ_VERSION=harmonic \
  --name ros2_sitl ros2_sitl:jazzy "$@"
