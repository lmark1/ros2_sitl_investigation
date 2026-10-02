#!/bin/bash
# Start this tmuxinator session. Run it INSIDE the container (./docker_run.sh on the host).
#   ./start.sh                 attach to the session
#   ./start.sh --no-attach     start in the background (tmux attach -t <name> later)
cd "$(dirname "$0")"
if [ ! -f /root/ros2_sitl_env.sh ]; then
  echo "Run this inside the ros2_sitl container: on the host run ros2_sitl/docker_run.sh first."; exit 1
fi
/root/ros2_sitl/kill_sim.sh >/dev/null 2>&1   # one simulation at a time: they share the ports
tmuxinator start -p session.yml "$@"
