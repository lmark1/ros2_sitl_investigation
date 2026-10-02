# ROS 2 integration plan: uav_ros_simulation and uav_ros_stack

Status 2026-09-30. How to turn the proof of concept in this repo into the real thing:
ROS 2 Jazzy branches of `uav_ros_simulation`, `uav_ros_stack` and their gitman
dependencies that a developer uses exactly like the Noetic ones today
(`./run_docker.sh`, `cd startup/kopterworx_one_flying && ./start.sh`).

Inputs: `ros2_sitl_findings.md` (what works and why), a read-only survey of both repos
as cloned on 2026-09-16 (uav_ros_simulation e0a890d, uav_ros_stack 3982760, locked
gitman revisions), and probes of the firmware fork run on 2026-09-30.
Not surveyed: `uav_ros_drivers` (gitman group `drivers`, not installed in the image).

## 1. Target

| | today | after |
|---|---|---|
| OS / ROS | Ubuntu 20.04, Noetic, catkin | Ubuntu 24.04, Jazzy, colcon (ament_cmake) |
| Simulator | Gazebo Classic 11 | Gazebo Harmonic (gz-sim 8, from the Jazzy apt vendor packages) |
| Firmware | larics/ardupilot `Larics-4.4.3` | larics/ardupilot `Larics-4.6.3` (exists: Copter-4.6.3 + yaw-rate patch + GUIDED_NOGPS enabled) |
| FCU interface | mavros (ROS 1) | mavros2 2.15 (decided in step 2). No AP_DDS, no micro-ROS agent. |
| Motor physics | ArduPilotPlugin -> `mav_msgs/Actuators` -> rotors `gazebo_motor_model` | ArduPilotPlugin -> `gz.msgs.Actuators` -> `MulticopterMotorModel` (same parameters) |
| User workflow | tmuxinator sessions in `startup/` | the same sessions, `roslaunch` -> `ros2 launch`, no `roscore` pane |

Rule for the whole port: **keep names**. Package names, launch file names and
arguments, topic and service names, `UAV_NAMESPACE`, session layout, test scenario.
A developer's muscle memory and the docs should survive; only the ROS version changes.

## 2. What has to move (sizes from the survey)

| Repo / package | Content | Port effort driver |
|---|---|---|
| uav_ros_simulation | install scripts, 2 Dockerfiles, run_docker.sh, 6 tmuxinator sessions, CI (build + rostest) and CD (binary images), docs | scripts and CI, no code |
| ardupilot_gazebo (larics fork, Classic) | ArduPilotPlugin 1330 lines, gimbal plugin, 13 launch files, run_copter.sh, automatic_takeoff.sh, mavros config, 8 param files, models: kopterworx, broli, hawk, bebop, ardrone, zephyr, iris, rover; `util/multirotor_base.urdf.xacro` 1033 lines of macros | replaced by upstream gz plugin + our patch; models and launch are the work |
| rotors_simulator, mav_comm | only 4 rotors plugins used (motor_model, multirotor_base, odometry, wind), only `mav_msgs/Actuators` | **dropped** on Jazzy |
| larics_gazebo_worlds | 11 worlds, 28 models, 35 launch files, 1 own plugin (sun direction) | world conversion, materials |
| uav_ros_msgs | 24 msg, 10 srv, 2 action | mechanical; 4 field renames (PIDController `P I D U`) |
| uav_ros_lib | 6.5k lines C++, 14 libraries, 3 dynamic_reconfigure cfg, tf1 in attitude_converter, links `mavros/frame_tf.h`, rosbag recorder | foundation: param, topic, reconfigure, transform handlers |
| uav_ros_control | 9.7k lines C++ (+18k generated CVXGEN C), 11 nodes, 2 nodelets, 3 controller plugins, 5 cfg, actionlib, 15 launch | the core of the port |
| uav_ros_tracker | 4.1k lines C++ (+39k CVXGEN), 1 nodelet, 4 plugins, topp_tracker.py, 3 launch | second |
| topp_ros | 1.4k lines Python, 2 srv, TOPP-RA from pip | small |
| uav_ros_general | 2.4k C++, 1.1k Python, 42 launch, mostly hardware wrappers | hardware phase |
| uav_ros_tests | one integration scenario (gtest + rostest), run by both repos' CI | the acceptance test |

Hand-written totals: about 23k lines C++, 3.4k lines Python, 76 launch files, 9
dynamic_reconfigure configs, 3 nodelets, 7 pluginlib plugins, 2 actions.

Existing ROS 2 attempts (all stale, none complete): `uav_ros_msgs/ros2` (2024-01, 35
commits behind main), `uav_ros_lib/humble-dev` (2025-07, 54 behind, lacks
transform_handler, recorder, profiler), `uav_ros_control/ros2` (2022, 174 behind, PID
library and carrot node only). `topp_ros/ros2` is not a port.

## 3. Facts the plan rests on

Verified in the PoC (see findings):
- Kopterworx flies on Harmonic with its Noetic motor constants and `kopterworx_v432.params`;
  hover matches the analytic value (0.452 of PWM range).
- mavros2 exposes the same topics and services the stack uses. Two gotchas: the
  setpoint_raw plugin needs `thrust_scaling` set explicitly, and stream rates need a
  link that honours the request.
- The stack's AttitudeTarget (`type_mask` 3, attitude + yaw rate) is rejected by stock
  ArduPilot. It needs the larics yaw-rate patch.
- One plugin patch is required (`patches/ardupilot_gazebo_actuators.patch`, 57 lines).
- Headless: real time factor 1.0, 20 s per arm/takeoff/land cycle, works without a GPU
  when no rendering sensors are loaded.

Verified on 2026-09-30:
- `Larics-4.4.3` does **not** build on Ubuntu 24.04: its waf and its pymavlink both
  import `imp`, removed in Python 3.12. Moving to `Larics-4.6.3` avoids carrying fixes.
- `Larics-4.6.3` (f277d13) = Copter-4.6.3 + "Add yawrate" + "Enable mode20 (guided no
  GPS)". It has the JSON SITL backend. **Not on it**: the 4.4.3 land-detector fix
  (926a0dc, cherry-picks cleanly onto 4.6.3), the AP_Logger change and the firmware
  name (both conflict, probably obsolete).
- 4.6.3 has the waf that works on Python 3.12, but its pymavlink generator still does
  `from future import ...`; Ubuntu's `python3-future` 0.18 breaks on 3.12, so the image
  needs `pip install "future>=1.0"`. Expected to build then, **not yet built**.
- 4.6.3 has the mandatory "Chute has no relay" arming check, so the sim needs
  `CHUTE_ENABLED 0` on top of the aircraft parameter file.
- The fork has no need for `Tools/ros2/ardupilot_sitl`: SITL keeps starting through
  `sim_vehicle.py` (today's `run_copter.sh`), which only needs `--model JSON` added.
- mavros2 ships `mavros/frame_tf.hpp` with the functions `uav_ros_lib` uses.

## 4. Repositories and branches

Noetic stays untouched on `main` / `larics-master`. Every repo gets a long-lived
`jazzy` branch; gitman files on the jazzy branches point at jazzy revisions.

| Repo | New branch | Based on |
|---|---|---|
| larics/uav_ros_simulation | `jazzy` | `main`; gitman `simulation` group loses rotors_simulator and mav_comm, `ardupilot` -> `Larics-4.6.3` |
| larics/uav_ros_stack | `jazzy` | `main` |
| larics/ardupilot_gazebo | `larics-jazzy` | **upstream** ArduPilot/ardupilot_gazebo `ros2` branch + Actuators patch + resource-path hook fix, then the larics models, launch, scripts, config copied in from `larics-master`. Package name stays `ardupilot_gazebo`, so `ros2 launch ardupilot_gazebo kopterworx.launch.xml` mirrors today. |
| larics/ardupilot | `Larics-4.6.3` | exists |
| larics/larics_gazebo_worlds | `jazzy` | `master` |
| uav_ros_msgs, uav_ros_lib, uav_ros_control, uav_ros_tracker, uav_ros_general, uav_ros_tests, topp_ros | `jazzy` each | `main`/`master`. For msgs and lib, port from main and use the old `ros2`/`humble-dev` branches as reference for solved problems, not as the base (they are 35 and 54 commits behind). |

While both exist: bug fixes land on `main` first and are cherry-picked to `jazzy`;
new features are agreed per case. The switch (jazzy becomes default, Noetic goes to
maintenance) happens after milestone M5.

One branch with ROS 1/ROS 2 conditionals is not proposed: nodelets, dynamic_reconfigure,
launch and the build system differ too much for shared sources to stay readable.

## 5. Where the proof of concept goes

| PoC artifact | Destination |
|---|---|
| `patches/ardupilot_gazebo_actuators.patch` | commit on `ardupilot_gazebo@larics-jazzy`; also propose upstream |
| `ros2_sitl_env.sh` resource path workaround | one line in the ardupilot_gazebo env hooks (`share` on `GZ_SIM_RESOURCE_PATH` and `SDF_PATH`); also propose upstream |
| `kopterworx_gz/scripts/gen_model.py` (generated SDF) | **dropped**. Its numbers already come from `kopterworx_base.urdf.xacro`; the xacro stays the source, only the plugin blocks in `util/multirotor_base.urdf.xacro` change |
| `kopterworx_gz/config/kopterworx_bridge.yaml` | `ardupilot_gazebo/config/`, loaded by `spawn_kopterworx.launch.xml`. The PoC's Python launch files were removed on 2026-10-02 in favour of the tmuxinator sessions. |
| `kopterworx_sitl_overrides.parm` | `ardupilot_gazebo/config/sitl_overrides.parm`, appended by `run_copter.sh` |
| `startup/kopterworx_flat/session.yml`, `startup/shell_helpers.sh`, `startup/README.md` | the template for `uav_ros_simulation/startup/` on jazzy: same panes, each command replaced by the corresponding launch file (table at the end of `startup/README.md`); the wait helpers go into the repo shell scripts |
| `kill_sim.sh`, `dex.sh` | not needed: `tmux kill-session` and `run_docker.sh` |
| `scripts/hover_test.py`, `cycle_test.py` | sim-only smoke test in uav_ros_simulation CI (launch_testing), runs before the stack test |
| `scripts/attitude_test.py` | firmware interface regression test (mask 3 on `Larics-4.6.3`) |
| `Dockerfile`, `docker_run.sh --nogpu` | basis of `Dockerfile.source` on jazzy and a `--noble-nogpu` mode of `run_docker.sh`; AP_DDS, micro-ROS agent, DDS-Gen, ardupilot_gz and SITL_Models are removed |
| `ros2_sitl_findings.md` | `uav_ros_simulation/docs/ROS2_MIGRATION.md` |

## 6. Milestones

Estimates are rough, for one engineer who knows the stack, derived from the sizes in
section 2. Each milestone ends with a test that either passes or does not.

### M0. Foundations and spikes (about 1 week)
Close the unknowns before anyone ports code.
1. Build `Larics-4.6.3` SITL on Ubuntu 24.04 (with `future>=1.0`), fly the PoC kopterworx
   against it through `sim_vehicle.py --model JSON`.
2. Run `attitude_test.py --type-mask 3` on it: must climb, pitch, yaw. This proves the
   stack's output format works unchanged.
3. mavros2 through MAVProxy's udp 14550 output with `--streamrate=50`, as the sessions
   do today. If the rates do not follow (the PoC saw 2 Hz on a MAVProxy link started
   without `--streamrate`), connect mavros to SITL SERIAL1 (tcp 5762 + 10 per instance).
4. Spawn the kopterworx from its **URDF xacro** with gz plugin blocks
   (`ros_gz_sim create -topic robot_description`). Confirm the IMU link survives fixed
   joint lumping (the model already uses a zero-limit revolute joint for that) and the
   ArduPilotPlugin finds `imu_link::imu_sensor`. Fallback if URDF conversion gets in
   the way: the same macros as `model.sdf.xacro`.
5. Decide the land-detector fix (section 8) and pick the parameter file for 4.6.
6. Create the branches, the jazzy gitman files, a first `Dockerfile.source`.

Exit: hover and attitude tests pass on `Larics-4.6.3` from a xacro-spawned kopterworx.

### M1. Simulation without the stack (2 to 3 weeks)
`uav_ros_simulation@jazzy` + `ardupilot_gazebo@larics-jazzy`.
- `util/multirotor_base.urdf.xacro`: replace plugin blocks (table in section 7.1).
  Kopterworx default configuration first: body, 4 rotors, IMU, odometry, front depth
  camera.
- Launch files, same names and arguments: `sim_vehicle`, `mavros`, `mavros_node`,
  `kopterworx`, `spawn_kopterworx`, `empty_world`. All XML, no Python (section 7.3).
- `run_copter.sh`: add `--model JSON`, append the SITL overrides. `fdm_port_out`
  disappears (JSON uses one port, 9002 + 10 per instance).
- `shell_scripts.sh` helpers on the ROS 2 CLI (`waitForRos`, `waitForSimulation` on
  `/clock`, `waitForOdometry`, ...), `automatic_takeoff.sh`.
- mavros config: `apm_config_NAMESPACE.yaml` to the ROS 2 parameter layout,
  `thrust_scaling` set explicitly.
- `installation/*.sh` for 24.04, `Dockerfile.source`, `run_docker.sh --noble`.
- Session `kopterworx_one_flying` with the simulation panes only.
- CI job: build + headless hover smoke test.

Exit: `./start.sh` brings up Gazebo, SITL and mavros; `hover_test` passes in CI.

### M2. Stack core: the default flying session (5 to 6 weeks)
Order follows the dependency graph.
1. `uav_ros_msgs`: rosidl, actions, rename `PIDController` fields to lower case.
2. `uav_ros_lib`: parameter, topic, reconfigure and transform handlers (section 7.2),
   attitude_converter off tf1, estimators, global_to_local on `mavros/frame_tf.hpp`.
3. `uav_ros_control`, node path first because the sessions and the integration test use
   it: `carrot_reference_node`, `pid_cascade_node`, `geo_fence_node`, launch
   `pid_carrot`, `carrot_reference`, `position_control`.
4. `topp_ros` and `uav_ros_tracker/topp_tracker.py` (rclpy), `topp_tracker.launch`.
5. Session `kopterworx_one_flying` complete.

Exit: the onboarding flight works on Jazzy: `./start.sh`, automatic takeoff to 2 m,
`ros2 topic pub --once /red/tracker/input_pose ...` moves the UAV.

### M3. Acceptance test, CI, images (1 to 2 weeks)
- `uav_ros_tests`: the same scenario (3 cycles of takeoff to 2 m, random tracker pose,
  land; 0.3 m tolerances) as `launch_testing` + gtest. Its test description is the only
  Python launch file in the port.
- CI in both repos on the jazzy branches: build, SITL build, smoke test, integration
  test, headless without rendering sensors. CD: `yonx/uav_ros_stack:noble-bin-<tag>`,
  `yonx/uav_ros_simulation:noble-bin-<tag>`, source images `:noble`, `:noble-nogpu`.
- Parity run against Noetic: same trajectory in both, compare hover throttle and
  tracking error. This is where the `thrust_multiplier` question gets closed.

Exit: CI green on jazzy with the integration test; parity numbers written down.

### M4. The rest of the simulation feature set (3 to 4 weeks)
- ControlManager and UAVManager as `rclcpp_components`, controller plugins (both PID
  variants, MPC with its CVXGEN code unchanged), actions on `rclcpp_action`,
  `mpc_tracker`, WaypointManager and its task plugins.
- Sessions: `kopterworx_one_flying_mpc_tracker`, `double_flying`, `triple_flying`
  (multi-vehicle: section 7.1).
- Lidar macro (needs the LiDAR-X definition from `velodyne_simulator`), gimbal, FPV camera.
- `larics_gazebo_worlds`: `empty` first, then the worlds in use (section 7.4).

Exit: every session in `startup/` that is still wanted starts and flies.

### M5. Hardware side and switch-over (3 to 4 weeks plus flight days)
- `uav_ros_general`: `apm2`/`px4` mavros launch, rc_to_joy, rc_override, estimators,
  status and monitoring, then sensor wrappers one by one as their ROS 2 drivers are
  confirmed (ouster, velodyne, robosense, cartographer, zed, vrpn, gremsy, openzen).
  multimaster is dropped, ROS 2 discovery replaces it.
- `uav_ros_drivers` (not surveyed yet).
- Onboard image for 24.04, bench test on a Pixhawk, then a flight with the real
  kopterworx on `Larics-4.6.3`.
- Docs (README, ONBOARDING, HOWTO, PACKAGES), default branch switch, Noetic to maintenance.

### M6. Long tail, on demand
Tilt rotors and manipulator (`gz_ros2_control`), dipole magnet (no gz port exists),
rotors wind plugin, other vehicles (hawk, broli, bebop, ardrone, zephyr), Unity/AirSim
session, remaining worlds.

Roughly 12 to 16 weeks to the end of M4 and 4 to 5 months to the switch, for one person.
M1 and M2.1/M2.2 can run in parallel with two people.

## 7. How to port, concretely

### 7.1 Simulation model and wiring

| Classic (in `multirotor_base.urdf.xacro` and friends) | Harmonic |
|---|---|
| `librotors_gazebo_motor_model.so` x4 | `gz-sim-multicopter-motor-model-system`, same parameters; `actuator_number` = ArduPilot channel (rotor 0 -> 0, rotor 1 -> 2, rotor 2 -> 1, rotor 3 -> 3) |
| `libArduPilotPlugin.so` with `controlTopicName` | upstream `ArduPilotPlugin` + `ACTUATOR` channels + `<actuators_topic>/<ns>/command/motor_speed` |
| Gazebo imu sensor + `libgazebo_ros_imu_sensor.so` | `<sensor type="imu">`; the plugin reads it directly, bridge only if a node needs it |
| `librotors_gazebo_odometry_plugin.so` (`odometry_plugin_macro`) | `gz-sim-odometry-publisher-system` + bridge to `/<ns>/odometry`; local macro, `rotors_description` no longer included |
| `librotors_gazebo_multirotor_base_plugin.so` | `gz-sim-joint-state-publisher-system` |
| `libgazebo_ros_openni_kinect.so` | `rgbd_camera` sensor + bridge (image, depth, points, camera_info) |
| `libgazebo_ros_camera.so` | `camera` sensor + bridge |
| velodyne `LiDAR-X` xacro | `gpu_lidar` sensor macro + bridge to `velodyne_points` |
| `libGazeboGimbalPlugin.so` | joint position controllers + bridge, or a small port (M4) |
| `libgazebo_ros_control.so` | `gz_ros2_control` (M6) |
| `librotors_gazebo_wind_plugin.so`, dipole magnet | M6 |
| `gazebo_ros spawn_model -urdf` | `ros_gz_sim create -topic robot_description` |
| `empty_world.launch` (gzserver, gzclient) | `ros_gz_sim gz_sim.launch.py`, world with physics, sensors, imu, navsat, scene broadcaster, user commands systems and `<spherical_coordinates>` |

Multi-vehicle stays as today, per vehicle N (instance I = N-1): `sim_vehicle id:=N`,
spawn with `name:=<ns> fdm_port_in:=9002+10I`, mavros `fcu_url` on 14550+10I. New on
gz: topics are global, so everything model specific is namespaced by the model name
(actuators topic, odometry topic, sensor topics are already scoped), and one
`ros_gz_bridge` per vehicle runs inside the vehicle's ROS namespace.

### 7.2 Code: ROS 1 construct -> ROS 2, as it occurs in this stack

| Construct (count) | Port |
|---|---|
| `ros::NodeHandle` passed into libraries | `rclcpp::Node::SharedPtr` (or node interfaces) passed the same way; private `~` parameters become node parameters with a dotted prefix |
| `getParamOrThrow` in `param_util.hpp` (about 250 call sites) | keep the helper, implement as declare + get; call sites barely change |
| `dynamic_reconfigure` (9 cfg, generic `reconfigure_handler.hpp`) | parameters with descriptors and an on-set callback, behind the same `ReconfigureHandler` interface; `rqt_reconfigure` keeps working. UAVManager's reconfigure client becomes a `SetParameters` call |
| nodelets (ControlManager, UAVManager, WaypointManager) | `rclcpp_components`, loaded into one container; `nodelet_manager.launch` becomes a component container launch |
| pluginlib (3 controllers, 4 tracker plugins) | pluginlib exists unchanged in ROS 2; interface gets the node pointer instead of two NodeHandles |
| actionlib (TargetLand, TargetTakeoff) | `rclcpp_action` |
| `ros::Timer` (137), `ros::Rate` loops (24) | wall/ROS timers; the hard-coded 50 Hz loop in `CascadePID.cpp` becomes a timer |
| tf1 (`attitude_converter`, `tf2TransformStamped`, Python `tf.transformations`) | tf2 / `tf_transformations` |
| `ros::Time::now`, `ros::Duration` (170) | node clock, so `use_sim_time` works |
| `TopicHandler` watchdogs | same class on rclcpp subscriptions + timer |
| rosbag recorder in uav_ros_lib | rosbag2 API, or drop in favour of `ros2 bag record` |
| `ROS_INFO` etc. (534), boost pointers | mechanical |
| rospy nodes (25) | rclpy; start with `topp_tracker.py` and topp_ros, the rest with M5 |
| CVXGEN C sources (57k generated lines) | compile unchanged. The generated headers carry CVXGEN's non-commercial notice, unchanged by the port |
| TOPP-RA pinned pip commit | move to a release that supports Python 3.12 |

Behavioural differences to handle deliberately, not mechanically:
- No global parameter server: `rosparam set use_sim_time true` in the sessions becomes
  a `use_sim_time` argument on every launch file.
- QoS: mavros publishes sensor topics best effort; subscribers in `TopicHandler` must
  match or they silently receive nothing.
- Service calls from inside callbacks deadlock on a single threaded executor; the
  managers call mavros services from timers and callbacks (32 clients in control),
  so they need callback groups and a multi threaded executor.

### 7.3 Launch files (76): XML, no Python
All our launch files stay XML, using the ROS 2 XML launch frontend (`*.launch.xml`).
mavros2 ships its own launch files the same way. They are not the literal ROS 1 files,
but each translates nearly line by line:

| ROS 1 | ROS 2 XML |
|---|---|
| `$(arg x)` | `$(var x)` |
| `$(find pkg)` | `$(find-pkg-share pkg)` |
| `<node pkg= type= ns=>` | `<node pkg= exec= namespace=>` |
| `<group ns="x">` | `<group><push-ros-namespace namespace="x"/>` ... |
| `<rosparam command="load" file=>` | `<param from=>` |
| `<param name="robot_description" command="xacro ...">` | `<param name="robot_description" value="$(command 'xacro ...')"/>` |
| `pkg="nodelet"` manager / load | `<node_container>` / `<load_composable_node>` |
| `rosparam set use_sim_time true` (in the sessions) | `<set_use_sim_time value="true"/>` once per launch file |
| scripts as nodes (`run_copter.sh`) | `<executable cmd=...>` |
| `<arg>`, `<include>`, `<remap>`, `$(env UAV_NAMESPACE)`, `$(eval ...)`, `if`/`unless`, `launch-prefix` | unchanged |

Checked against the Jazzy frontend in the container (2026-09-30): it exposes `arg`,
`let`, `include`, `group`, `node`, `executable`, `node_container`,
`load_composable_node`, `push-ros-namespace`, `set_use_sim_time`, `set_parameter`,
`set_remap`, `set_env`, `timer`, and the substitutions `var`, `env`, `find-pkg-share`,
`command`, `eval`, `if`, `equals`, `not`, `and`, `or`, `anon`, `file-content`. That
covers everything the 76 files use, including xacro processing, the spawn
(`<node pkg="ros_gz_sim" exec="create" args="-topic robot_description -name $(var name) ..."/>`)
and the per-vehicle port arithmetic (`$(eval '9002 + 10 * instance')`). The Python
spawn launch of the proof of concept is not carried over.

Python remains in exactly two places:
- **The integration test.** `launch_testing` only accepts a Python test description.
  One file of about 30 lines in `uav_ros_tests` that includes the XML launch and
  replaces `kopterworx_base_rostest.launch`.
- **Upstream files we include but do not own**, such as `ros_gz_sim/gz_sim.launch.py`.
  An XML `<include>` can include a Python launch file, so nothing of ours changes.

### 7.4 Worlds
gz worlds need the system plugins and spherical coordinates added, and Ogre 1 material
scripts (`gazebo.material`, 22 references) replaced by SDF materials. Models from the
Classic online database (`house_1`, `office_building`, `suv`, ...) need Fuel
equivalents or removal. The sun direction plugin needs a small gz port. Convert
`empty` in M1, the others by demand in M4/M6.

## 8. Risks and open points

| # | Risk / open point | Handling |
|---|---|---|
| 1 | `Larics-4.6.3` is not yet built or flown on 24.04 | M0 item 1, first thing |
| 2 | 4.4.3 land-detector fix (926a0dc) is not on `Larics-4.6.3` | check whether 4.6.3 still needs it; it cherry-picks cleanly |
| 3 | Parameter files are from 4.3.2/4.4.3 (`kopterworx_v432.params`, `tuned_v443.params`) | load on 4.6.3 in M0, list renamed or rejected parameters, produce a `kopterworx_v463.params` |
| 4 | mavros2 behaviour differences (thrust_scaling, stream rates, QoS) | M0 item 3, explicit config in the launch files |
| 5 | URDF xacro through the gz URDF converter | M0 item 4, fallback SDF xacro |
| 6 | Hover throttle differs from the value stored in the aircraft file (0.224 learned vs 0.290) | measure the Noetic sim in M3 parity run, then fix `thrust_multiplier` (667 or about 602) |
| 7 | External model dependencies with no gz version: `storm_gazebo_ros_magnet`, `velodyne_simulator` LiDAR-X, `aerial_manipulators_description` | lidar in M4 from its definition, magnet and manipulator in M6 |
| 8 | ROS 2 drivers for the onboard sensors | confirm per sensor at the start of M5 |
| 9 | Drift between `main` and `jazzy` during four months | cherry-pick rule in section 4, keep the port of each package short |
| 10 | The fork of ardupilot_gazebo diverges from upstream | upstream the Actuators patch and the hook fix so the fork carries only larics content |
| 11 | `uav_ros_drivers` unknown | survey it before M5 |

## 9. Decisions needed from you

1. **Control paths.** The sessions and the integration test use the node path
   (`pid_carrot`: carrot_reference_node + pid_cascade_node); ControlManager/UAVManager
   is the newer nodelet path. The plan ports the node path first (M2) and the managers
   in M4. If one of them is meant to be retired, say so and the port shrinks.
2. **Scope of v1.** Kopterworx only, with camera, and lidar in M4. Which other vehicles,
   worlds and sessions are still in use?
3. **Noetic hover number**, to close `thrust_multiplier`.
4. **Land-detector fix** on `Larics-4.6.3`: needed or obsolete?
5. **Upstream PRs** for the plugin patch and the env hook: yes or keep in the fork.
6. **Who and when**: one or two people, and the date after which `jazzy` is the default.
