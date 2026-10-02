# Bringup: what runs, why, and how it is connected

Bringup is done with tmuxinator sessions, like `uav_ros_simulation/startup/` on Noetic.
Every process has its own pane and every pane shows the real command. Nothing is
hidden inside a launch file.

| Session | What it is | Use it to |
|---|---|---|
| `kopterworx_flat/` | Kopterworx on the motor-model path, SITL through `sim_vehicle.py`, mavros. No upstream launch, no AP_DDS. | **Copy this into uav_ros_simulation.** |
| `iris_flat/` | The upstream iris with exactly the same panes. | See that the wiring is model independent. `diff` the two session files: only model, parameters and bridge config differ. |
| `iris_upstream/` | The upstream way: one `ros2 launch` starts everything, including AP_DDS. | Understand what the upstream launch hides. Not the target. |

```bash
# host
cd ros2_sitl && ./docker_run.sh
# inside the container
cd /root/ros2_sitl/startup/kopterworx_flat && ./start.sh
```

`GUI=false ./start.sh` skips the Gazebo window, `HEADLESS=true ./start.sh` renders the
camera with EGL when there is no X display, `./start.sh --no-attach` starts in the
background (`tmux attach -t kopterworx_flat`). `/root/ros2_sitl/kill_sim.sh` stops
everything. One session at a time, they share the ports.

All three were run on 2026-10-02 and hover (kopterworx 3 m at 0.452 of the PWM range,
iris 3 m at 0.561), with mavros at 50 Hz.

## The picture

Six processes. Two belong to the autopilot side, three to the simulator side, mavros
sits between the autopilot and ROS.

```
 AUTOPILOT SIDE                                                   ROS 2 SIDE
 (window "sitl")
                         MAVLink                    MAVLink
 +------------------+   tcp 5760   +-----------+   udp 14550   +-----------+  /mavros/state
 |  arducopter      |<------------>| MAVProxy  |<------------->|  mavros   |  /mavros/local_position/*
 |  (SITL, window   |   RC input   | (pane     |               |  (pane    |  /mavros/setpoint_raw/attitude
 |   "ardupilot1")  |<-------------| sim_vehi- |               |  mavros)  |  /mavros/cmd/arming, set_mode
 +------------------+   udp 5501   | cle)      |               +-----------+
     |          ^                  +-----------+
     | servo    | JSON reply: IMU, pose,                         your nodes, the test scripts
     | PWM      | velocity, sim time
     v          |
   udp 127.0.0.1:9002
 ...............|..........................................................................
 SIMULATOR SIDE |  (window "gazebo")
 +--------------|---------------------- gz sim server (pane server) ----------------------+
 |  +-----------+------+  gz.msgs.Actuators                +--------------------------+   |
 |  | ArduPilotPlugin  |---------------------------------->| MulticopterMotorModel x4 |   |
 |  | (in the model)   |  /kopterworx/command/motor_speed  | thrust + drag on rotors  |   |
 |  +------------------+                                   +--------------------------+   |
 |        ^ reads                                                                         |
 |  imu sensor            OdometryPublisher          rgbd camera        physics (1 kHz)    |
 +------|-------------------------|---------------------------|--------------------------+
        |                         | gz topics                 |               ^
   world systems:        /model/kopterworx/odometry   .../sensor/camera/*    | gz transport
   physics, sensors,              |                           |          +--------+
   imu, navsat           +--------v---------------------------v---+      | gz sim |
        ^                |  ros_gz_bridge parameter_bridge        |      |  -g    |
        | create         |  (pane bridge)                         |      | (pane  |
        | service        +--------|-------------------------------+      |  gui)  |
 +------+---------+               v ROS 2 topics                         +--------+
 | ros_gz_sim     |      /clock  /odometry  /camera/*  /joint_states
 | create         |
 | (pane spawn)   |
 +----------------+
```

The two things that make it "our" simulation rather than the upstream demo:

1. **Motor path.** The ArduPilot plugin does not move the rotors itself. It publishes the
   four motor speeds as one `gz.msgs.Actuators` message, and four
   `MulticopterMotorModel` systems turn them into thrust with motor dynamics. This is
   what rotors_simulator did on Classic. It needs the plugin patch in `../patches/`.
   The iris uses the upstream path instead: the plugin runs a PID on each rotor joint.
2. **Autopilot link.** ROS talks to the autopilot through mavros only. No AP_DDS, no
   micro-ROS agent.

## Pane by pane

Window `sitl`:

| Pane | Command | Why it exists | Talks to | Noetic equivalent |
|---|---|---|---|---|
| `sim_vehicle` | `sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON -I0 --add-param-file=... -m "--streamrate=50"` | Starts the autopilot and MAVProxy. `--model JSON` selects the interface the Harmonic plugin speaks. | Starts `arducopter` in window `ardupilot1` and MAVProxy in this pane. | `sim_vehicle.launch` -> `run_copter.sh` (same call, without `--model JSON`) |
| window `ardupilot1` | `arducopter --model JSON --defaults <files> --sim-address=127.0.0.1 -I0` | The flight controller firmware itself. | Sends servo PWM to udp 9002, serves MAVLink on tcp 5760, 5762, 5763, takes RC on udp 5501. | the detached `ardupilot1` window |
| (in `sim_vehicle`) | `mavproxy.py --master tcp:127.0.0.1:5760 --sitl 127.0.0.1:5501 --out 127.0.0.1:14550 --streamrate 50` | Ground station. Feeds RC input to SITL, forwards MAVLink, gives you a prompt (`mode guided`, `arm throttle`, `param show X`). | SITL tcp 5760, mavros udp 14550 | same |
| `mavros` | `ros2 launch mavros apm.launch fcu_url:=udp://:14550@localhost:14555` | MAVLink to ROS 2. The stack's only interface to the autopilot. | Binds udp 14550. | `mavros.launch`, same `fcu_url` |
| `mavros_setup` | `ros2 param set /mavros/setpoint_raw thrust_scaling 1.0` | mavros 2.15.1 starts with this unset and then silently sends thrust 0 for every AttitudeTarget. | mavros | not needed on ROS 1 |

Window `gazebo`:

| Pane | Command | Why it exists | Talks to | Noetic equivalent |
|---|---|---|---|---|
| `server` | `gz sim -s -r <world>.sdf` | Physics and sensors. The world file loads the physics, sensors, imu and navsat systems and sets the GPS origin. | everything below, over gz transport | `gzserver` inside `kopterworx.launch` |
| `gui` | `gz sim -g` | The window. Optional. | server | `gzclient` |
| `spawn` | `ros2 run ros_gz_sim create -world runway -name kopterworx -file model.sdf -z 0.35` | Inserts the vehicle into the running world. The model brings the ArduPilot plugin and the motor models with it. Exits when done. | server's create service | `spawn_model` in `spawn_kopterworx.launch` |
| `bridge` | `ros2 run ros_gz_bridge parameter_bridge --ros-args -p config_file:=...` | Gazebo topics are not ROS topics. This copies the ones we need: `/clock`, `/odometry`, `/camera/*`, `/joint_states`. | server (gz), ROS 2 | not needed on Classic, plugins published ROS topics directly |

Window `fly`: a status pane that waits for each link in turn and prints `[ok]` lines, and
a pane with the test commands.

## Start order and how to check each link

Order between the windows does not matter. SITL keeps sending servo packets until the
plugin answers, mavros waits for MAVLink, the bridge waits for the server.

| Link | It works when | If not |
|---|---|---|
| Gazebo server | `gz topic -l` shows `/clock` | world file path or missing plugin, read pane `server` |
| Model | `gz model --list` shows the model | pane `spawn`; "Unable to find uri" means a resource path problem |
| SITL <-> plugin | window `ardupilot1` printed `JSON received:` once and is quiet | repeating "No JSON sensor message received" = model not spawned or plugin not loaded |
| Motor path (kopterworx) | `gz topic -e -n 1 -t /kopterworx/command/motor_speed` prints four velocities | plugin patch missing, or channels not `ACTUATOR` |
| SITL <-> MAVProxy | MAVProxy prints `AP: EKF3 IMU0 is using GPS` | SITL not started, see window `ardupilot1` |
| MAVProxy <-> mavros | `ros2 topic echo /mavros/state --once` shows `connected: true` | wrong `fcu_url` or port taken by another session |
| Rates | `ros2 topic hz /mavros/local_position/pose` is about 50 | MAVProxy started without `--streamrate=50` gives 2 Hz |
| Bridge | `ros2 topic hz /clock` and `/odometry` | bridge yaml names do not match world or model name |

Other failures seen while building this, with their cause:

| Symptom | Cause |
|---|---|
| Arming refused, "Gyros not calibrated" | SITL started without `copter.parm`. ArduPilot master's `sim_vehicle.py` no longer adds the frame's default files when `--model` is JSON, so the sessions list them. Check on `Larics-4.6.3` whether it still adds them itself, as 4.4.3 did. |
| Arming refused, "Chute has no relay" | the aircraft parameter file enables a parachute on a relay, SITL has no relay: `kopterworx_sitl_overrides.parm` |
| Vehicle armed, AttitudeTarget sent, never leaves the ground | `thrust_scaling` unset in mavros, see pane `mavros_setup` |
| AttitudeTarget with attitude + yaw rate is ignored | stock ArduPilot rejects it, the larics yaw-rate patch is needed (`Larics-4.6.3` has it, the master binary in this image does not) |

## Iris and kopterworx side by side

| | `iris_flat` | `kopterworx_flat` |
|---|---|---|
| Model | upstream `ardupilot_gazebo/models/iris_with_gimbal` | `kopterworx_gz/models/kopterworx` (generated by `scripts/gen_model.py`) |
| Motor path | plugin runs a velocity PID on each rotor joint, lift-drag plugins make thrust | plugin publishes `Actuators`, `MulticopterMotorModel` makes thrust |
| PWM range in the model | 1100 to 1900 (`gazebo-iris-gimbal.parm` sets `MOT_PWM_MIN/MAX`) | 1000 to 2000 |
| Parameter files, in order | `copter.parm`, `gazebo-iris-gimbal.parm`, `sitl_no_dds.parm` | `copter.parm`, `gazebo-iris.parm`, `kopterworx_v432.params`, `kopterworx_sitl_overrides.parm`, `sitl_no_dds.parm` |
| Bridge config | `ardupilot_gz_bringup/config/iris_bridge.yaml` | `kopterworx_gz/config/kopterworx_bridge.yaml` |
| Spawn | z 0.2, yaw 90 deg | z 0.35 |
| Hover, mean motor output | 0.561 | 0.452 |

## What the upstream launch starts that we do not need

`iris_upstream/session.yml` lists the nine processes behind
`ros2 launch ardupilot_gz_bringup iris_runway.launch.py`. Compared with the flat sessions:

- `micro_ros_agent`: transport for AP_DDS. Not used, the stack talks through mavros.
- `robot_state_publisher` and the `gz/tf` relay: publish the model and TF. Not needed to
  fly. The real port keeps the xacro and `robot_state_publisher` (see below).
- SITL is started as a bare `arducopter` process plus a MAVProxy without a prompt and
  without `--streamrate`, instead of through `sim_vehicle.py`. That is why mavros there
  has to use tcp 5762 and request the rates itself.

## What changes when this moves into uav_ros_simulation

The panes stay, the commands become the launch files the Noetic sessions already call.

| Pane here | In uav_ros_simulation (jazzy) |
|---|---|
| `sim_vehicle` | `ros2 launch ardupilot_gazebo sim_vehicle.launch.xml` -> `run_copter.sh` with `--model JSON` |
| `mavros` + `mavros_setup` | `ros2 launch ardupilot_gazebo mavros.launch.xml`, `thrust_scaling` in its parameter yaml, topics under `/$UAV_NAMESPACE/mavros` |
| `server`, `gui`, `spawn`, `bridge` | `ros2 launch ardupilot_gazebo kopterworx.launch.xml` (= `empty_world` + `spawn_kopterworx`) |
| `spawn` with `-file model.sdf` | xacro -> `robot_state_publisher` -> `ros_gz_sim create -topic robot_description` |
| model name `kopterworx`, topics without namespace | model name and namespace `$UAV_NAMESPACE` (red) |
| `sitl_no_dds.parm` | not needed, the fork is built without DDS |
| `shell_helpers.sh` | `waitForRos`, `waitForSimulation`, `waitForOdometry` in the repo's shell scripts |

## Ports

| Port | Owner | Purpose |
|---|---|---|
| udp 9002 | ArduPilot plugin inside gz server | servo packets from SITL in, JSON state back |
| tcp 5760 | arducopter | MAVLink SERIAL0, used by MAVProxy |
| tcp 5762, 5763 | arducopter | MAVLink SERIAL1, SERIAL2, free |
| udp 5501 | arducopter | RC input from MAVProxy |
| udp 14550 | mavros | MAVLink forwarded by MAVProxy |

A second vehicle adds 10 to each (`sim_vehicle.py -I1`, plugin `fdm_port_in` 9012).
