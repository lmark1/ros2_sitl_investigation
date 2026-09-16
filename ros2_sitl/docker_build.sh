#!/bin/bash
# Build the ros2_sitl image. Private repos are cloned through the host ssh-agent
# (--ssh default), the key never enters the image. Extra args go to docker build,
# e.g. ./docker_build.sh --progress=plain
set -e
export DOCKER_BUILDKIT=1
cd "$(dirname "$0")"
docker build --ssh default -t ros2_sitl:jazzy "$@" .
