# ROS 2 SITL investigation

ArduPilot + Gazebo Harmonic SITL on ROS 2 Jazzy, next to the existing ROS 1 Noetic
setup. Everything runs in one docker image, nothing is installed on the host.

- `ros2_sitl_investigation.md`: the plan.
- `ros2_sitl_findings.md`: what was found, step by step (baseline commits, mavros2 vs
  AP_DDS, the kopterworx port, headless timing, every patch and failure).
- `ros2_integration_plan.md`: how to move this into `uav_ros_simulation` and
  `uav_ros_stack` for real (branches, milestones, per-package porting notes, risks).
- `ros2_sitl/`: the docker setup, the kopterworx package, helper scripts.

## Prerequisites (host)

- docker with buildx, nvidia-container-toolkit for the GPU (optional, see `--nogpu`).
- ssh-agent running with a key that can read `larics/uav_ros_simulation` and
  `larics/uav_ros_stack` (`ssh-add -l` shows it). The key is never copied anywhere,
  the build uses `--ssh default`, the container gets the agent socket.

## Build

```bash
cd ros2_sitl
./docker_build.sh              # ~20 min the first time, image ros2_sitl:jazzy (17 GB)
```

What the image contains (see the Dockerfile, one layer per step):
Jazzy desktop-full with Gazebo Harmonic, ArduPilot build tools, Micro-XRCE-DDS-Gen,
the two private repos plus their gitman deps (reference only), a ROS 2 workspace built
from `ros2_gz.jazzy.repos` (ardupilot master, ardupilot_gazebo ros2, ardupilot_gz,
SITL_Models, micro-ROS agent, all pinned to the commits that were tested), mavros2, the
ArduPilotPlugin patch and `kopterworx_gz`.

## Run

```bash
cd ros2_sitl
./docker_run.sh -d             # create + start detached (GPU, X forwarded)
./docker_run.sh                # attach a shell (repeat in more terminals)
./docker_run.sh --nogpu -d     # same image without GPU/X, for the CI case
./dex.sh 'ros2 topic list'     # run one command inside with ROS sourced
```

This folder is mounted at `/root/ros2_sitl` inside the container. Logs of every
launch go to `ros2_sitl/logs/` (gitignored).

### Fly something

Bringup is a tmuxinator session, one process per pane, as in `uav_ros_simulation/startup/`.
**Read `ros2_sitl/startup/README.md`**: it has the wiring diagram, what every pane is
for, how to check each link and what changes in the real integration.

Inside the container:

```bash
cd /root/ros2_sitl/startup/kopterworx_flat && ./start.sh   # kopterworx, the bringup to copy
cd /root/ros2_sitl/startup/iris_flat && ./start.sh         # upstream iris, same panes
cd /root/ros2_sitl/startup/iris_upstream && ./start.sh     # upstream one-launch demo with AP_DDS, for comparison

GUI=false ./start.sh          # no Gazebo window
HEADLESS=true ./start.sh      # render camera/lidar with EGL, no X display needed
./start.sh --no-attach        # background, then: tmux attach -t kopterworx_flat
/root/ros2_sitl/kill_sim.sh   # stop everything

# container without a GPU (started on the host with ./docker_run.sh --nogpu)
LIBGL_ALWAYS_SOFTWARE=1 MESA_GL_VERSION_OVERRIDE=3.3 GUI=false HEADLESS=true ./start.sh
```

Windows of the flat sessions:

| window | panes |
|---|---|
| `sitl` | `sim_vehicle` (SITL + MAVProxy prompt), `mavros`, `mavros_setup` |
| `ardupilot1` | the `arducopter` process, opened by `sim_vehicle.py` |
| `gazebo` | `server`, `gui`, `spawn`, `bridge` |
| `fly` | `status` (prints `[ok]` per link), `test` (commands to run) |

### Test scripts (`ros2_sitl/scripts/`, run inside the container)

```bash
python3 /root/ros2_sitl/scripts/hover_test.py --alt 3        # GUIDED, arm, takeoff, hover, LAND; prints z, attitude, motor PWM, hover throttle
python3 /root/ros2_sitl/scripts/cycle_test.py --alt 3        # times one arm/takeoff/land cycle, wall vs sim clock
python3 /root/ros2_sitl/scripts/attitude_test.py --type-mask 7   # AttitudeTarget at 50 Hz through mavros (GUIDED_NOGPS)
python3 /root/ros2_sitl/scripts/roll_probe.py 10             # ground truth roll vs motor commands at 5 Hz
```

Useful topics: `/mavros/local_position/pose`, `/mavros/global_position/local`,
`/mavros/rc/out`, `/odometry` (Gazebo ground truth), `/camera/image`,
`/velodyne_points`, `/ap/...` (AP_DDS).

## The kopterworx package (`ros2_sitl/kopterworx_gz`)

- `models/kopterworx/model.sdf` is generated, do not edit it. Change the numbers at
  the top of `scripts/gen_model.py` and run it (`--lidar` adds the lidar,
  `--no-camera` drops the camera), then `colcon build --packages-select kopterworx_gz`
  in `/root/ros2_ws` (the source dir is symlinked to this folder in a running
  container, the image has a copy).
- Motor path: ArduPilotPlugin `ACTUATOR` channels publish one `gz.msgs.Actuators` on
  `/kopterworx/command/motor_speed`, four `MulticopterMotorModel` systems (same
  parameters as the rotors_simulator motor model) do the motor dynamics. This needs
  `ros2_sitl/patches/ardupilot_gazebo_actuators.patch`, applied in the Dockerfile.
- `config/kopterworx_v432.params` is the aircraft file, `config/kopterworx_sitl_overrides.parm`
  what SITL on ArduPilot master needs on top (parachute off, trims zero).
- No launch files. Bringup is `startup/kopterworx_flat/session.yml`; `config/kopterworx_bridge.yaml`
  is the gz to ROS bridge configuration it uses.

## Layout

```
ros2_sitl/
  Dockerfile, docker_build.sh, docker_run.sh   image and container
  ros2_gz.jazzy.repos                          workspace sources (Jazzy variant of upstream ros2_gz.repos)
  ros2_sitl_env.sh                             sourced in the container (ROS, GZ, resource paths)
  startup/                                     tmuxinator sessions + README with the wiring diagram
  kill_sim.sh, dex.sh                          stop / exec helpers
  config/                                      small SITL parameter files used by the sessions
  patches/                                     ArduPilotPlugin Actuators patch
  kopterworx_gz/                               the ported model, ament package
  scripts/                                     test scripts
  ref/                                         upstream files kept for reference
  logs/                                        launch and test logs (gitignored)
```
