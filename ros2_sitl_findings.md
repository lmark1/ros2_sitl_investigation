# ROS 2 SITL findings

Working notes for the plan in `ros2_sitl_investigation.md`. Dates are absolute.
Sections follow "What to write down" in the plan.

## Host (2026-09-16)

- Docker 29.8.0 with buildx v0.37.0, nvidia-container-toolkit hook present
  (`/usr/bin/nvidia-container-runtime-hook`), `docker run --gpus all` verified on
  RTX 4070 Laptop, driver 580.126.09. No `nvidia` runtime registered in
  `docker info`, not needed: `--gpus` goes through the hook.
- ssh-agent has two keys loaded, `ssh -T git@github.com` authenticates as lmark1.
- Noetic container `pcl_ris` (image `pcl_ris:focal`, host network) is running and
  is left alone. None of the SITL ports (5760, 9002/9003, 14550, 2019) are in use.

## Deviations from the plan doc (checked against ArduPilot docs, 2026-09-16)

- ArduPilot wiki `ros2-install.html` still says "ROS 2 Humble is the only version
  supported". The ardupilot repo itself ships `Tools/ros2/ros2.jazzy.repos` and its
  `Tools/ros2/README.md` says Humble or Jazzy. Staying on Jazzy as the plan says.
- `ardupilot_gz/ros2_gz.repos` pins `ros_gz`, `sdformat_urdf` and `micro_ros_agent`
  to `humble` branches. On Jazzy those would not build against the Jazzy base. Using
  a local repos file instead (`ros2_sitl/ros2_gz.jazzy.repos`): `ros_gz` and
  `sdformat_urdf` from the Jazzy apt binaries already in `osrf/ros:jazzy-desktop-full`
  (ros_gz 1.0.22, gz-sim 8.11.0 vendor packages), `micro_ros_agent` from its `jazzy`
  branch (same as ardupilot's `ros2.jazzy.repos`). ardupilot_gz has no CI, so there is
  no upstream tested combination to copy.
- The plan's Dockerfile omits Micro-XRCE-DDS-Gen (needed by the `ardupilot_sitl`
  colcon package to build SITL with `--enable-DDS`) and the ArduPilot build
  prerequisites (empy, pexpect, future, ...). Added, following
  `ardupilot_dev_docker/docker/Dockerfile_dev-ros`.
- rosdep keys `gz-cmake3`, `gz-sim8`, `gz-plugin2`, `gz-common5` have no Ubuntu
  definition on the Jazzy base. Adding the osrf `00-gazebo.list` would map them to the
  non-vendor Harmonic debs and mix two Gazebo installs. They are skipped in rosdep,
  the vendored packages satisfy CMake once `/opt/ros/jazzy` is sourced.
- `ros2_ws` is not bind mounted (plan asked to pick one): the workspace built into
  the image is what runs. `ros2_sitl/` is mounted at `/root/ros2_sitl` for scripts
  and logs.

## Baseline (image, commits, apt versions) - 2026-09-16

Image `ros2_sitl:jazzy` from `ros2_sitl/Dockerfile`, base `osrf/ros:jazzy-desktop-full`
(ros-jazzy-desktop-full 0.11.0-1noble.20260616). Ubuntu 24.04, ROS 2 Jazzy, Gazebo
Sim 8.11.0 (Harmonic, `ros-jazzy-gz-sim-vendor` 0.0.10).

Workspace `/root/ros2_ws` from `ros2_sitl/ros2_gz.jazzy.repos`, commits that flew:

| repo | branch | commit |
|---|---|---|
| ArduPilot/ardupilot | master | b2b1b3d279614af0f4b55ad7a5e497691aaad9e2 (ArduCopter V4.8.0-dev) |
| ArduPilot/ardupilot_gazebo | ros2 | cc0290d964dfa373531963a8fc39093a0836af0a |
| ArduPilot/ardupilot_gz | main | 8df4dc1726e37504e6fc8b952d02e554cfa3176f |
| ArduPilot/SITL_Models | main | d5d6017367a509b77886379c91207edc66f77652 |
| micro-ROS/micro-ROS-Agent | jazzy | 7c932329ad5591ef23942ef1962534258c16b000 |
| ArduPilot/Micro-XRCE-DDS-Gen | master | 4bc7ec2c7f77ae89cd216432f05470ad99f7faa1 |
| gazebosim/ros_gz | apt | ros-jazzy-ros-gz-sim / -bridge 1.0.22-1noble.20260615 |
| ros/sdformat_urdf | apt | ros-jazzy-sdformat-urdf 1.0.2-1noble.20260604 |

Other: MAVProxy 1.8.74, pymavlink 2.4.49, gitman 3.8.1. Private repos in the image:
uav_ros_simulation e0a890d (main), uav_ros_stack 3982760 (main), gitman "simulation"
group: larics/ardupilot 34af6c4 (Larics-4.4.3), larics/ardupilot_gazebo 3cdfe0b
(larics-master), rotors_simulator e683629, mav_comm 260be94, larics_gazebo_worlds 7885901.

Build times on this host (24 cores): gitman install 416 s, DDS-Gen 45 s, vcs import
299 s, rosdep 108 s, colcon build of 8 packages 346 s (ardupilot_sitl 4 min 12 s,
micro_ros_agent 1 min 32 s).

## Step 1: upstream iris - flies (2026-09-16)

`ros2 launch ardupilot_gz_bringup iris_runway.launch.py rviz:=false` inside the
container, GUI on the host display through the GPU.

- First attempt did not spawn the vehicle at all. robot_state_publisher died
  ("Unable to find uri[package://ardupilot_gazebo/models/iris_with_standoffs]") so
  `ros_gz_sim create -topic robot_description` waited forever, and spawning the same
  SDF with `-file` failed inside the gz server with the same unresolved include. SITL
  kept printing "No JSON sensor message received". Cause: the `ardupilot_gazebo` env
  hooks add `share/ardupilot_gazebo/models` and `worlds` to `GZ_SIM_RESOURCE_PATH` and
  `SDF_PATH` but not `<prefix>/share`, which is what a `package://ardupilot_gazebo/...`
  URI resolves against. `ardupilot_gz_description` adds that line for itself,
  `ardupilot_gazebo` does not. Upstream: ArduPilot/ardupilot_gazebo#109 (closed, "use
  the ros2 launch"), the launch does not fix it either on Jazzy. Fix, no source patch:
  `ros2_sitl_env.sh` appends `/root/ros2_ws/install/ardupilot_gazebo/share` to both
  `GZ_SIM_RESOURCE_PATH` (gz server) and `SDF_PATH` (sdformat_urdf inside
  robot_state_publisher). Both verified separately, then the full launch.
- The launch does not use `sim_vehicle.py` (the plan doc says it does). It starts
  `arducopter --model json` directly plus a non-interactive `mavproxy.py` that only
  forwards to udp 14550/14551. A console is attached with
  `mavproxy.py --master udp:127.0.0.1:14550` (in a tmux window here).
- DDS topics are under `/ap/v1/...` not `/ap/...`: the launch loads
  `dds_use_ns.parm` (DDS_USE_NS 1), the plan doc's topic names are the un-namespaced
  form.
- MAVProxy: `mode guided`, `arm throttle` (arming checks are disabled by the default
  params), `takeoff 3` -> `/ap/v1/pose/filtered` z = 2.99 m, Gazebo `/odometry` z =
  3.19 m (spawned 0.2 m above the runway).
- Rates measured with `ros2 topic hz` (window 200):

| topic | Hz |
|---|---|
| /ap/v1/pose/filtered, /ap/v1/twist/filtered | 10.5 |
| /ap/v1/imu/experimental/data | 75 |
| /ap/v1/navsat | 2 |
| /ap/v1/time | 30 |
| /ap/v1/clock | 34 |
| /clock (bridge) | 498 |
| /imu (bridge, gz sensor) | 536 |
| /odometry (bridge) | 17 |
| /navsat (bridge) | 11 |

- Bridged Gazebo topics (`iris_bridge.yaml`): clock, joint_states, odometry
  (`/model/iris/odometry`), gz/tf, camera image + info, air_pressure, imu,
  magnetometer, navsat, gpsfix, battery. `/odometry` is the ground truth equivalent
  of our `/$UAV_NAMESPACE/odometry`.

### Motor path of the upstream iris (checked in ardupilot_gazebo ros2 @ cc0290d)

The launch spawns `iris_with_gimbal`, which merges `iris_with_standoffs` and adds the
ArduPilotPlugin. It uses the **joint PID path** (path 1 in the plan): each of the four
`<control>` channels has `<type>VELOCITY</type>`, `<useForce>1</useForce>`,
`<p_gain>0.20</p_gain>`, `<i_gain>0</i_gain>`, `<d_gain>0</d_gain>`, driving
`rotor_N_joint` through `gz-sim-apply-joint-force-system`, and thrust comes from one
`gz-sim-lift-drag-system` per blade side (eight instances). No
`gz-sim-multicopter-motor-model-system` anywhere in ardupilot_gazebo or SITL_Models.

The `<type>COMMAND</type>` + `<cmd_topic>` control type does exist in the upstream
plugin (`ArduPilotPlugin.cc`, load at line ~629, apply at ~1317), but it publishes a
`gz.msgs.Double` per channel, not a `gz.msgs.Actuators`. Upstream only uses it for the
gimbal servos (`/gimbal/cmd_roll` etc., `iris_with_gimbal/model.sdf`) and for a few
SITL_Models (blueboat, catamaran, hexapod_copter). `MulticopterMotorModel` subscribes
to `gz.msgs.Actuators` on `commandSubTopic` and indexes it by `motorNumber`, so the
plan's diagram (ArduPilotPlugin -> Actuators on /<model>/command/motor_speed ->
MulticopterMotorModel) is not what upstream provides. For step 3 this means: the
motor-model path needs either a small plugin change (publish all motor channels as one
`gz.msgs.Actuators`, which is what the larics classic fork does with
`mav_msgs/Actuators`) or a relay system from N Double topics to one Actuators message.
The plugin part is not a big port, the control loop and the JSON interface stay.

### AP_DDS control on this baseline (see step 2 for details)

Services present: `/ap/v1/arm_motors`, `/ap/v1/mode_switch`, `/ap/v1/prearm_check`,
`/ap/v1/experimental/takeoff`, `/ap/v1/get_parameters`, `/ap/v1/set_parameters` (the
last two are newer than the AP_DDS README list). Cycle run from the hover at 3 m:

```
ros2 service call /ap/v1/mode_switch ardupilot_msgs/srv/ModeSwitch "{mode: 9}"   # LAND
  -> z 0.0, /ap/v1/status armed false, mode 9
ros2 service call /ap/v1/mode_switch ardupilot_msgs/srv/ModeSwitch "{mode: 4}"   # GUIDED
ros2 service call /ap/v1/arm_motors ardupilot_msgs/srv/ArmMotors "{arm: true}"
ros2 service call /ap/v1/experimental/takeoff ardupilot_msgs/srv/Takeoff "{alt: 5.0}"
  -> /ap/v1/pose/filtered z 4.99, /odometry z 5.19
```

MAVProxy console shows the matching "AP: DDS: Request for ... : SUCCESS" lines.

### State at the end of step 1

Container `ros2_sitl` is running (`./docker_run.sh` attaches), tmux session `sim`
inside it: window `launch` (the ros2 launch, log in `ros2_sitl/logs/launch_iris_2.log`)
and window `mav` (MAVProxy console on udp 14550). The iris is hovering at 5 m in
GUIDED. `ros2_sitl/kill_sim.sh` stops everything.

## Step 2: mavros2 vs AP_DDS

TODO

## ArduPilot version and the fork

TODO

## Step 3: kopterworx port

Not started.

## Step 4: headless timing

Not started.

## Patches and failures

(none yet)
