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
SITL_Models, micro-ROS agent), mavros2, the ArduPilotPlugin patch and `kopterworx_gz`.

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

Inside the container:

```bash
# upstream iris (step 1 baseline)
/root/ros2_sitl/start_sim.sh

# kopterworx with its own params (step 3)
export KW_PARMS=/root/ros2_sitl/kopterworx_gz/config/kopterworx_v432.params,/root/ros2_sitl/kopterworx_gz/config/kopterworx_sitl_overrides.parm
/root/ros2_sitl/start_sim.sh kopterworx_gz kopterworx_runway.launch.py

# headless (no Gazebo window, camera/lidar rendered with EGL)
/root/ros2_sitl/start_sim.sh kopterworx_gz kopterworx_runway.launch.py use_gz_sim_gui:=false headless_rendering:=true

# no GPU at all (inside the --nogpu container)
EXTRA_ENV="LIBGL_ALWAYS_SOFTWARE=1 MESA_GL_VERSION_OVERRIDE=3.3" /root/ros2_sitl/start_sim.sh kopterworx_gz kopterworx_runway.launch.py use_gz_sim_gui:=false headless_rendering:=true
```

`start_sim.sh` kills any previous sim and opens a tmux session `sim` with three windows:

| window | what |
|---|---|
| `launch` | `ros2 launch ...` (Gazebo server + GUI, spawn, SITL, micro-ROS agent, ros_gz bridge) |
| `mav` | MAVProxy console on udp 14550 (`mode guided`, `arm throttle`, `takeoff 3`, `param show X`) |
| `mavros` | mavros2 on SITL SERIAL1 (tcp 5762), streams at 50 Hz, `thrust_scaling` set |

`tmux attach -t sim` to look at them, `/root/ros2_sitl/kill_sim.sh` to stop everything.

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
- `launch/kopterworx_runway.launch.py` (world + vehicle) and `launch/kopterworx.launch.py`
  (spawn + SITL + DDS agent, wraps the upstream `robot.launch.py`).

## Layout

```
ros2_sitl/
  Dockerfile, docker_build.sh, docker_run.sh   image and container
  ros2_gz.jazzy.repos                          workspace sources (Jazzy variant of upstream ros2_gz.repos)
  ros2_sitl_env.sh                             sourced in the container (ROS, GZ, resource paths)
  start_sim.sh, kill_sim.sh, dex.sh            run / stop / exec helpers
  config/sitl_extra.parm                       SITL params appended to every launch (SERIAL1_BAUD)
  patches/                                     ArduPilotPlugin Actuators patch
  kopterworx_gz/                               the ported model, ament package
  scripts/                                     test scripts
  ref/                                         upstream files kept for reference
  logs/                                        launch and test logs (gitignored)
```
