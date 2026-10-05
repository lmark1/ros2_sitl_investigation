# ROS 2 SITL findings

Working notes for the plan in `ros2_sitl_investigation.md`. Dates are absolute.

Note 2026-10-02: `start_sim.sh` and the Python launch files of `kopterworx_gz`, which
the sections below mention, were replaced by tmuxinator sessions in
`ros2_sitl/startup/` (see its README). The measurements stand; to reproduce them use
`startup/kopterworx_flat` or `startup/iris_upstream` with `GUI=false HEADLESS=true`.
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

## Step 2: mavros2 vs AP_DDS (2026-09-16, ArduPilot master b2b1b3d = 4.8.0-dev)

Helpers: `ros2_sitl/start_sim.sh` (launch + MAVProxy + mavros in tmux, inside the
container), `ros2_sitl/scripts/attitude_test.py` (the AttitudeTarget test),
`ros2_sitl/config/sitl_extra.parm` (appended to the launch `defaults`).

### A. mavros2 (`ros-jazzy-mavros` 2.15.1, `ros-jazzy-mavlink` 2026.8.8)

- Installed with apt inside the container plus
  `install_geographiclib_datasets.sh`. Now in the Dockerfile.
- Link: `fcu_url:=tcp://127.0.0.1:5762` (SITL SERIAL1). Through the launch's
  MAVProxy forward on udp 14551 mavros connects too but every stream stays at
  2 Hz and `set_stream_rate` has no effect there. On the direct tcp link
  `set_stream_rate {stream_id: 0, message_rate: 50}` works.
- Topics: 136 `/mavros/*` topics, the ones the stack uses exist with the ROS 1
  names: `/mavros/global_position/local`, `/mavros/local_position/pose`,
  `/mavros/local_position/velocity_local`, `/mavros/imu/data`, `/mavros/state`,
  `/mavros/setpoint_raw/attitude`, `/mavros/rc/override`; services
  `/mavros/set_mode`, `/mavros/cmd/arming`, `/mavros/cmd/takeoff`, `/mavros/cmd/land`,
  `/mavros/set_stream_rate`, `/mavros/param/*`.
- Rates, wall clock, `ros2 topic hz`: 25 Hz for global_position/local,
  local_position/pose, velocity_local, imu/data, imu/data_raw, battery, with the
  stream rate at 50. Not a MAVLink limit: SERIAL1_BAUD 1500 (via
  `sitl_extra.parm`) and `set_message_interval` 50 Hz change nothing. Gazebo runs
  at real time factor 0.46 with the GUI on this laptop (`/world/runway/stats`,
  sim clock advanced 6 s in 10 s wall), and SITL is in lockstep with it, so 50 Hz
  in sim time is 25 Hz wall. Same effect on the DDS side. Headless (step 4) will
  show what the machine can do.
- `thrust_scaling`: the setpoint_raw plugin came up with `thrust_scaling = nan`
  although `apm_config.yaml` sets 1.0 and other values from that file are
  applied. With nan the plugin logs "Received thrust, but ignore_thrust is true"
  and sends thrust 0, so ArduPilot never gets a positive climb rate and never
  leaves the ground. `ros2 param set /mavros/setpoint_raw thrust_scaling 1.0`
  at runtime fixes it (now in start_sim.sh). No matching upstream issue found
  (mavros#1178 only added the yaml line).
- Attitude test, GUIDED_NOGPS, arm, AttitudeTarget at 50 Hz, thrust 0.7 climb /
  0.5 hover (GUID_OPTIONS 0, thrust field = climb rate), then LAND:

| type_mask | result |
|---|---|
| 3 (IGNORE_ROLL_RATE + IGNORE_PITCH_RATE, quaternion + body yaw rate, **what uav_ros_control sends**) | never leaves the ground, auto disarm after 10 s. Master `GCS_MAVLink_Copter.cpp` handle_set_attitude_target: a partial rate mask hits `hold_position(); return;` before `set_angle`. |
| 7 (all rates ignored, yaw integrated into the quaternion on the ROS side) | climb to 4.3 m in 3 s, pitch -5 deg gives 4 m/s forward, yaw follows 0.5 rad/s (89 -> -131 deg in 8 s), LAND lands and disarms. |

  No RC input or RC override is needed: `angle_control_run` sets `auto_armed`
  itself on a positive climb rate (same on the 4.4.3 fork). The larics fork commit
  07fb299 "Add yawrate" is exactly what makes mask 3 work on 4.4.3 (adds
  `use_yaw_rate` to `ModeGuided::set_angle`, 12 lines). Master still does not have
  it. So on any upstream ArduPilot either that patch is carried over or the stack
  sends mask 7 and integrates the yaw rate itself (the test script does this).

### B. AP_DDS (ardupilot master, `libraries/AP_DDS`)

- What exists (topic table + `ros2 node info /ap`), published: time, clock,
  navsat, tf_static, battery, imu/experimental/data, pose/filtered,
  twist/filtered, geopose/filtered, gps_global_origin/filtered, airspeed, rc,
  status, goal_lla. Subscribed: joy (RC override, up to 8 channels),
  cmd_vel (TwistStamped, GUIDED velocity), cmd_gps_pose (GlobalPosition), tf
  (external odometry), /clock. Services: arm_motors, mode_switch, prearm_check,
  experimental/takeoff, get_parameters, set_parameters.
- **No attitude and thrust setpoint.** `AP_DDS_ExternalControl` has only
  `handle_global_position_control` and `handle_velocity_control`. Nothing in the
  library mentions attitude, thrust or rates. The cascade PID / MPC output has
  nowhere to go on the DDS side; `/ap/joy` is a stick override, not a setpoint.
- Rates, wall clock, at the same RTF 0.46: pose/filtered 10.5, twist/filtered 10.5,
  imu 75, navsat 2, time 30, clock 34 Hz (step 1 table). Periods are compile-time
  constants (`AP_DDS_DELAY_*_TOPIC_MS`), generated by `gen_config_h.py`.
- ArduPilot versions (first Copter tag containing the code): AP_DDS itself and
  cmd_vel / global position control 4.5.0, parameter services 4.7.0. The topic
  namespace changed between runs: `/ap/v1/...` in one run and `/ap/...` after a
  SITL restart in another with the same `DDS_USE_NS 1` default file. Not chased.
- Caveats seen: a `reboot` from MAVProxy crashed SITL (dumpcore) in this launch
  setup, restart the launch instead. The ArduPilotPlugin logs "controller has
  reset" several times per run, flight was fine.

### Summary for the decision (not a pick)

| | mavros2 | AP_DDS |
|---|---|---|
| attitude + thrust setpoint | yes, `setpoint_raw/attitude` | no |
| odometry for the stack | `global_position/local` etc, 50 Hz sim time | `pose/filtered` + `twist/filtered`, 10 Hz fixed |
| mode / arm / land | same services as ROS 1 | mode_switch / arm_motors / takeoff |
| ArduPilot needed | any, 4.4.3 fork works as is | >= 4.5, parameters >= 4.7 |
| stack changes | none for the interface, the fork's yaw-rate patch is still needed unless the stack moves to mask 7 | new interface, and the controllers have no output |
| extra gotchas | `thrust_scaling` must be set, direct tcp link for stream rates | namespace behaviour, fixed rates |

## ArduPilot version and the fork

- Baseline runs ArduPilot master (4.8.0-dev). The fork is 4.4.3 with three
  commits on top: land detector internal-error fix (926a0dc), "Add yawrate"
  (07fb299, the mask-3 support above), an AP_Logger line commented out (49e6658).
  `GUID_OPTIONS` is a stock parameter, the kopterworx params set it to 0.
- For option A the fork can stay on 4.4.3 (JSON backend exists there, not tested
  yet against gz-sim, step 3). For option B the fork has to move to >= 4.5, and
  the yaw-rate patch would still be needed for the mavros path.

## Step 3: kopterworx port (2026-09-16, mavros chosen for the interface)

Package `ros2_sitl/kopterworx_gz` (ament, SDF, no xacro): `models/kopterworx/model.sdf`
is GENERATED by `scripts/gen_model.py` (all numbers at the top of that script, taken
from `kopterworx_base.urdf.xacro`), `launch/kopterworx_runway.launch.py` (runway world
+ vehicle), `launch/kopterworx.launch.py` (spawn + SITL + DDS agent through
`ardupilot_gz_bringup/launch/robots/robot.launch.py`), `config/kopterworx_bridge.yaml`,
`config/kopterworx_v432.params` (copy), `config/kopterworx_sitl_overrides.parm`.
Run inside the container:

```
export KW_PARMS=/root/ros2_sitl/kopterworx_gz/config/kopterworx_v432.params,/root/ros2_sitl/kopterworx_gz/config/kopterworx_sitl_overrides.parm
/root/ros2_sitl/start_sim.sh kopterworx_gz kopterworx_runway.launch.py
python3 /root/ros2_sitl/scripts/hover_test.py --alt 3
```

### Motor model path: plugin patch (the one patch of the port)

`ros2_sitl/patches/ardupilot_gazebo_actuators.patch` (57 lines on ardupilot_gazebo ros2
@ cc0290d, applied in the Dockerfile): new control `<type>ACTUATOR</type>` and a
plugin level `<actuators_topic>`. All ACTUATOR channels go out as one
`gz.msgs.Actuators` (index = channel, value = cmd = pwm mapped to [0,1] times
`<multiplier>`), published every ApplyMotorForces. This is the gz equivalent of the
larics classic fork's `controlTopicName` / `mav_msgs/Actuators` path. The
ArduPilot-to-rotor channel swap of the classic publish order `[c0, c2, c1, c3]` is not
in the plugin any more, it is the `<actuator_number>` of each MulticopterMotorModel
(rotor 0 front_right ccw = channel 0, rotor 1 front_left cw = channel 2, rotor 2
back_left ccw = channel 1, rotor 3 back_right cw = channel 3). No upstream issue or
PR exists for this (searched ardupilot_gazebo for Actuators / MulticopterMotorModel /
motor_speed). Worth proposing upstream, it does not change existing behaviour.

### Steps and results (all with `hover_test.py`: GUIDED, arm, takeoff 3 m, hover, LAND)

| step | model | SITL params | hover motor output (mean PWM, normalised) | note |
|---|---|---|---|---|
| 3.1a | upstream iris copy, unchanged (lift-drag + joint PID) | copter + gazebo-iris | 1562, 0.562 | plumbing check, flies |
| 3.1b | iris geometry on MulticopterMotorModel + ACTUATOR channels (X3 example constants, max 1100 rad/s) | copter + gazebo-iris | 1560, 0.563 | flies, but roll rate limit cycle: ±150 deg/s at ~1 Hz, motors saturating 1150/1830, roll angle only ±2 deg. Default ArduPilot rate gains vs a plant that answers in 12.5 ms (the upstream lift-drag iris is slowed by its torque clamped rotor PID). Not pursued, the iris plant is throwaway. |
| 3.2 | kopterworx geometry: 9 kg, xacro inertia, 0.52 m arms at 45 deg, rotors at z 0.115, kopterworx motor constants (2.4407e-4 N s^2, 0.04415 m, 12.5 ms, 667 rad/s, drag 8.06e-5), multiplier 667, servo 1000-2000, 0.3x0.3x0.6 collision box, mesh scale 0.1 | copter + gazebo-iris | 1452, 0.452 | no oscillation at all, motors flat, roll 0.0. Analytic hover sqrt(m g / 4 k) = 301 rad/s = cmd 0.451. |
| 3.3 | same | + kopterworx_v432.params + overrides | 1452, 0.452 | first attempt refused to arm: "Chute has no relay" (CHUTE_ENABLED 1 in the file, mandatory check on master, ARMING_CHECK 0 does not cover it). Override CHUTE_ENABLED 0. EKF showed a constant 1.5 deg roll from AHRS_TRIM_X -0.024 (aircraft calibration), overrides zero AHRS_TRIM_X/Y. Everything else in the 895 line file loads (FORMAT_VERSION ignored with a warning). |
| 3.4 | + OdometryPublisher system -> `/model/kopterworx/odometry` -> bridge `/odometry` (nav_msgs/Odometry, 50 Hz sim time) | | | `/odometry` z = 3.30 vs `/mavros/local_position/pose` z = 3.00: EKF origin is the spawn point 0.30 m up (collision box half height). x, y agree within 0.05 m. |
| 3.5 | + rgbd_camera "camera" on camera_link (0.2 0 0.05, 640x480, 30 Hz, noise 0.007, like the classic openni kinect depth camera), + gpu_lidar on lidar_link (classic velodyne pose, 440 x 16, +-15 deg, 1-50 m, 10 Hz) | | 1452, 0.452 | topics `/camera/image` 13.7 Hz, `/camera/depth_image` 20 Hz, `/camera/points` 8 Hz, `/velodyne_points` 9.1 Hz (wall clock, RTF 1.0 in that run). IMU noise: the classic kopterworx IMU is `gazebo_ros_imu_sensor` with `gaussianNoise 0.0`, so there is nothing to port, SITL adds its own sensor noise. The gz IMU sensor is left at upstream settings (1000 Hz, no noise). |

### Hover throttle vs Noetic, thrust_multiplier

- New sim: hover at 1452 PWM (0.452 of 1000-2000), ArduPilot learned `MOT_THST_HOVER`
  0.224 after one hover (MOT_HOVER_LEARN 2, MOT_THST_EXPO 0.65, MOT_SPIN_MIN/MAX
  0.13/0.95).
- The aircraft file carries `MOT_THST_HOVER 0.290`, which with the same expo and spin
  range corresponds to a hover PWM of about 1500 (0.50). The Noetic sim was not run
  here (its container is off limits); check there with `param show MOT_THST_HOVER`
  after a hover or read `mavros/rc/out`.
- Analytically 0.29 corresponds to a multiplier of about 602. Measured 2026-10-05 with a
  scratch copy of the model (see next section): 602 gives hover PWM 1501 and a learned
  `MOT_THST_HOVER` of 0.275, 667 gives 1452 and 0.225. Not changed, see the conclusion below.

### thrust_multiplier: what it is, where 667 comes from, whether to keep it (2026-10-05)

What it is. ArduPilot sends one PWM per motor. The plugin maps it to 0..1
(`servo_min`..`servo_max`) and multiplies by `<multiplier>`; the result is the rotor
speed reference in rad/s for the motor model. So the multiplier is **rotor speed at full
throttle**, nothing to do with thrust directly (thrust = motor_constant x speed^2). The
name `thrust_multiplier` is ours: argument of the `ardupilot` xacro macro in
larics/ardupilot_gazebo (a4d3060, 2020-04-24). Upstream calls it `<multiplier>` and every
upstream model has one (iris: 838). It cannot be removed, some number has to turn PWM
into rad/s.

Where 667 comes from.

- It is the model's `max_rot_velocity`. Same number in both places for kopterworx
  (667/667), broli (667/667), hawk (628.318/628.318), ardrone (1475/1475). Only bebop
  differs (1000 vs 1475). Both were changed together from 600 to 667 in 7a39b49
  (2022-12-05), the commit that also switched the propeller data from APC 22x11E to 22x8.
- `motor_constant` 2.4407e-4 and `moment_constant` 0.04415 are reproducible:
  `motor_parameters/get_thrust_and_torque_k.m` on `22x8.mat` (APC static data) gives
  2.440724618e-04 and 0.0441480777. (The script takes the quadratic coefficient of a full
  second order fit; a pure k w^2 fit gives 2.398e-4, 1.7 % lower.)
- 667 rad/s itself (6370 rpm) is **not** derived anywhere in the repo. No motor, ESC or
  battery data there. It implies 108.6 N (11.07 kgf) per motor, thrust to weight 4.9 at
  9 kg. The old 600 gives 87.9 N, thrust to weight 4.0.

Live check (kopterworx_flat, headless, clean eeprom, 50 s hover at 3 m):

| multiplier | hover PWM | plugin output | 4 k w^2 | weight (9.05 kg) | learned MOT_THST_HOVER |
|---|---|---|---|---|---|
| 667 (repo) | 1452 (0.452) | 301.48 rad/s | 88.74 N | 88.78 N | 0.225 |
| 602 (scratch copy) | 1501 (0.501) | 301.60 rad/s | 88.81 N | 88.78 N | 0.275 |

The conversion does what the code says, and the hover rotor speed is the same in both
runs, only the PWM that produces it moves. The aircraft file has `MOT_THST_HOVER` 0.290
(learned on the real aircraft). With 667 the simulated vehicle hovers at 22 % less
throttle than the real one; with 600 it is within 5 %. Which side is off (max rotor
speed, real mass above 9 kg, or real thrust below the APC static table) cannot be
decided from the repo; it needs one number from the real aircraft (hover PWM from a
flight log with the take-off mass, or max rpm of the motor and propeller).

What it affects.

- Hover throttle. ArduPilot learns it (`MOT_HOVER_LEARN 2`), so the vehicle flies either way.
- Plant gain seen by the rate loops: thrust per unit of command at hover is 97.9 N at 667
  and 88.4 N at 602, 10 % apart.
- Thrust headroom (4.9 vs 4.0).
- **Not** what the stack sends. `kopterworx_v432.params` has `GUID_OPTIONS 0`, so
  ArduPilot reads the thrust of an AttitudeTarget as a climb rate (0.5 = hold altitude),
  on master and on Larics-4.4.3 alike. The xacro comment "tuned in order for
  mavros/setpoint_raw/attitude/thrust to reflect real-world behavior" dates from the
  parameter sets with `GUID_OPTIONS 8` (thrust as thrust,
  `kopterworx_red_v41_thrust_compassless.params`), where the mavros thrust went straight
  to the motors. It is stale for the current parameters.

When it has to change. Only when the powertrain of the modelled aircraft changes (motor,
propeller, battery voltage), and then together with `max_rot_velocity`. Not for a ROS,
Gazebo or firmware version, not per world. If the two diverge: multiplier above
`max_rot_velocity` and the motor model clamps (classic `gazebo_motor_model.cpp:131`,
gz-sim8 `MulticopterMotorModel.cc:537`), so the top of the throttle range does nothing
and ArduPilot does not know; multiplier below and the maximum is never reached.

Conclusion. Keep the conversion, drop it as a separate knob: one constant,
`max_rot_velocity`, used for both the motor model and the plugin `<multiplier>`, no
macro argument, and a comment that says "rotor speed at full throttle". Whether 667 is
the right maximum is a question about the real aircraft, not about the port.

### What was not ported (by choice or not needed)

- gimbal, tilt rotors, manipulator, wind, bag, magnet, FPV camera, multirotor_base
  plugin (joint states come from `gz-sim-joint-state-publisher-system`).
- xacro: everything is one generated SDF. `ros-jazzy-xacro` exists if the variants are
  wanted later.
- LiDAR-X vertical layout: the `velodyne_description` fork is not in any of the
  cloned repos, so the lidar uses a VLP-16 like +-15 deg, 16 rings. Adjust in
  `gen_model.py` (`--lidar` to enable, off by default like the classic launch).

## Step 4: headless timing (2026-09-16)

Server only, no GUI: `start_sim.sh kopterworx_gz kopterworx_runway.launch.py
use_gz_sim_gui:=false headless_rendering:=true` (adds `--headless-rendering`, EGL, no X
needed). Cycle = `scripts/cycle_test.py`: GUIDED, arm, takeoff 3 m, 5 s hover, LAND,
wait for disarm. Wall clock vs sim clock (`/clock`) over the whole cycle. Kopterworx
with `kopterworx_v432.params`, this laptop (24 threads, RTX 4070 Laptop).

| config | container | RTF (gz stats) | cycle wall | cycle sim | sim/wall | camera image / points / lidar Hz (wall) |
|---|---|---|---|---|---|---|
| A: no rendering sensors, headless | GPU | 1.00 | 19.6 s | 19.6 s | 1.00 | - |
| B: camera + lidar, headless EGL on the GPU | GPU | 1.00 | 20.7 s | 19.6 s | 0.94 | 29.5 / 20.7 / 9.7 |
| C: camera + lidar, headless, **no GPU** (Mesa llvmpipe) | `docker_run.sh --nogpu` | 1.00 | 25.5 s | 18.1 s | 0.71 | 11.9 / 9.2 / 7.5 |

- Phases in A: armed after 0.6 s, at 3 m after 5.8 s, disarmed 8.8 s after LAND.
- With the GUI on, the same machine gave RTF 0.46 (step 2, iris) to 1.0 (step 3.5).
  Headless is at 1.0 for A and B. RTF 1.0 is Gazebo's real time target
  (`<real_time_factor>1.0</real_time_factor>` in runway.sdf), SITL runs in lockstep at
  speedup 1 (fixed in `robot.launch.py`), so faster than real time was not measured.
  That is the next lever for CI if 20 s per flight is too slow.
- C is the CI case. It needs a container without `/dev/dri`: with `--privileged` the
  host's NVIDIA device is visible, Mesa tries it and Ogre2 dies with "OpenGL 3.3 is
  not supported" / segfault. On the GPU container `LIBGL_ALWAYS_SOFTWARE=1` is refused
  by Mesa ("Not allowed to force software rendering when API explicitly selects a
  hardware device") and Ogre2 segfaults. `docker_run.sh --nogpu` drops `--gpus`,
  `--privileged` and X; then `EXTRA_ENV="LIBGL_ALWAYS_SOFTWARE=1 MESA_GL_VERSION_OVERRIDE=3.3"`
  for start_sim.sh. The gz server took 6.4 cores in C, so a 2 core CI runner will be
  well below 0.71.
- Sensor rates are rendering bound: image 29.5 Hz of 30 on the GPU, 11.9 Hz on
  llvmpipe. The lidar at 10 Hz is close in both.
- Suggested CI structure from these numbers: flight tests without rendering sensors
  (config A: 20 s per cycle, RTF 1.0 on any CPU), a separate sensor smoke test that
  only checks the camera and lidar topics exist and publish (no timing assertions),
  and a GPU runner only if image rate matters.

## Patches and failures

- `patches/ardupilot_gazebo_actuators.patch`: ArduPilotPlugin ACTUATOR channels +
  `<actuators_topic>` (gz.msgs.Actuators for MulticopterMotorModel). No upstream issue.
- `ros2_sitl_env.sh`: `<prefix>/share` of ardupilot_gazebo on `GZ_SIM_RESOURCE_PATH`
  and `SDF_PATH` (ArduPilot/ardupilot_gazebo#109, ArduPilot/ardupilot_gz#96).
- `kopterworx_sitl_overrides.parm`: CHUTE_ENABLED 0, AHRS_TRIM_X/Y 0 for SITL.
- mavros2 `thrust_scaling` set at runtime (nan from apm_config.yaml on
  ros-jazzy-mavros 2.15.1), see step 2.
- Failed and not pursued: MAVProxy `reboot` of SITL in this launch (crash),
  `set_stream_rate` through the MAVProxy udp forward (stays 2 Hz), software rendering
  inside the GPU container (Mesa refuses), iris on the motor model with default gains
  (roll rate limit cycle).

