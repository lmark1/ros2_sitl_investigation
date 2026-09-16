# ROS 2 SITL investigation

How to find out what it takes to run our ArduPilot + Gazebo SITL on ROS 2, before we
port any stack package. The output of this work is a running iris, then a running
kopterworx, and a short findings file with the decisions listed at the bottom.

Nothing here is verified yet. The commands come from the ArduPilot ROS 2 docs, so check
them against the docs page while you go:
https://ardupilot.org/dev/docs/ros2.html

## Where to run it

Not in the Noetic dev container. That container has no docker binary and no docker
socket, and you do not want to install ROS 2 next to Noetic anyway. Nested docker
(docker in docker) is not worth it either: you would need a privileged daemon inside the
container, a separate storage driver and GPU passthrough through two layers.

Run a second container next to the Noetic one, straight from the host. You start in an
empty folder on the host, so the first job is to build that container yourself.

### Repos you need

- `git@github.com:larics/uav_ros_simulation` (private). Holds the current SITL: the
  `ardupilot_gazebo` fork, `rotors_simulator`, the kopterworx model and the
  `kopterworx_v432.params` file. Its dependencies come in through gitman
  (`gitman.yml`, all `git@github.com:larics/...` URLs) so they also need SSH.
- `git@github.com:larics/uav_ros_stack` (private). The ROS 1 stack that has to be
  ported later. Needed here only for reference, for example `uav_ros_control` to see
  what goes out on `mavros/setpoint_raw/attitude`.
- `https://github.com/ArduPilot/ardupilot_gz`, `ArduPilot/ardupilot_gazebo`,
  `ArduPilot/ardupilot`, `gazebosim/ros_gz` (public).

Private repos are reached with the SSH agent from the host, same as our current
images do. Nothing gets copied into the image, the key stays on the host.

### Docker setup to create

Make a folder `ros2_sitl/` with a `Dockerfile`, `docker_build.sh` and `docker_run.sh`.
Mirror what `uav_ros_simulation/Dockerfile.source` and
`uav_ros_stack/docker_build.sh` do, just on a Jazzy base:

```dockerfile
# Dockerfile
# syntax=docker/dockerfile:1
FROM osrf/ros:jazzy-desktop-full

RUN apt-get update && apt-get install -y \
    git openssh-client python3-vcstool python3-colcon-common-extensions \
    python3-pip default-jre tmux tmuxinator vim \
    && rm -rf /var/lib/apt/lists/*

# SSH at build time: the key comes from the host agent through --ssh default,
# it is never written into the image.
RUN mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts

WORKDIR /root
RUN --mount=type=ssh git clone git@github.com:larics/uav_ros_simulation.git
RUN --mount=type=ssh git clone git@github.com:larics/uav_ros_stack.git

# gitman for the simulation dependencies (ardupilot fork, ardupilot_gazebo, rotors...)
RUN pip3 install --break-system-packages gitman
RUN --mount=type=ssh cd uav_ros_simulation && gitman install

# ROS 2 workspace with ArduPilot's packages
RUN mkdir -p /root/ros2_ws/src && cd /root/ros2_ws \
    && vcs import --recursive --input https://raw.githubusercontent.com/ArduPilot/ardupilot_gz/main/ros2_gz.repos src
RUN cd /root/ros2_ws && apt-get update && rosdep install --from-paths src --ignore-src -r -y \
    && rm -rf /var/lib/apt/lists/*
RUN cd /root/ros2_ws && . /opt/ros/jazzy/setup.sh && colcon build --packages-up-to ardupilot_gz_bringup

RUN echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc \
    && echo "source /root/ros2_ws/install/setup.bash" >> ~/.bashrc
CMD ["/bin/bash"]
```

```bash
# docker_build.sh
#!/bin/bash
export DOCKER_BUILDKIT=1
docker build --ssh default -t ros2_sitl:jazzy "$(dirname "$0")"
```

```bash
# docker_run.sh
#!/bin/bash
# Same flags as uav_ros_simulation/run_docker.sh, different image.
ln -sf $SSH_AUTH_SOCK ~/.ssh/ssh_auth_sock
docker run -it --network host --privileged \
  --gpus all --env NVIDIA_DRIVER_CAPABILITIES=all \
  --volume ~/.ssh/ssh_auth_sock:/ssh-agent --env SSH_AUTH_SOCK=/ssh-agent \
  --volume /tmp/.X11-unix:/tmp/.X11-unix:rw --env DISPLAY=$DISPLAY \
  --volume "$(pwd)/ros2_ws:/root/ros2_ws" \
  --name ros2_sitl ros2_sitl:jazzy
```

Build the Dockerfile up in steps, do not write all of it and then debug for an hour.
Get the base image with the two clones working first, then gitman, then the ROS 2
workspace. Each `RUN` that fails is a layer you can fix and rebuild from.

Notes:

- `--ssh default` on build and `RUN --mount=type=ssh` in the Dockerfile are what let the
  clones work. `ssh-keyscan github.com` before the first clone or git will hang on the
  host key prompt. Needs a running ssh-agent on the host with the GitHub key loaded
  (`ssh-add -l` shows it).
- `ln -sf $SSH_AUTH_SOCK ~/.ssh/ssh_auth_sock` before `docker run` and the
  `/ssh-agent` mount is what makes git work inside the running container (pulls,
  gitman updates). The socket path on the host changes between logins, the link
  gives it a stable name.
- `NVIDIA_DRIVER_CAPABILITIES=all` matters. The default nvidia runtime only gives you
  compute, and new Gazebo (OGRE2) needs OpenGL. Without it the GUI falls back to
  software rendering or does not start.
- `--network host` so SITL, Gazebo, MAVProxy and the DDS agent see each other on
  localhost, same as now.
- The `ros2_ws` volume shadows the one built in the image. Either drop that volume
  line and work inside the container, or bind mount and build once more inside. Pick
  one and say which in the findings file.
- Both containers can run at the same time. Just do not start roscore in one and expect
  the other to see anything, they are different middlewares.
- If the host has no nvidia-container-toolkit, drop the two GPU lines and export
  `LIBGL_ALWAYS_SOFTWARE=1` inside. Slow, but enough to see if things work.

## Versions to target

- Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic. This is what ArduPilot's own ROS 2
  packages are tested on and Jazzy is the LTS with the longest support.
- Gazebo Classic (what we run now) is end of life since January 2025. Do not spend time
  on it.
- ArduPilot: our fork is `larics/ardupilot` at `Larics-4.4.3`. The JSON SITL backend
  that new Gazebo uses exists in 4.4, so the fork works with the Gazebo side as is.
  The DDS interface (AP_DDS) only exists from 4.5 on. Keep this in mind for the
  decision below.

## How the current SITL is wired, and what to keep

Read this before step 1 so you know what "works" means for us.

Today the vehicle in Gazebo Classic is built from two pieces:

- `ros_packages/ardupilot_gazebo` (larics fork): `src/ArduPilotPlugin.cc`. Talks to
  SITL over UDP (ports 9002/9003), receives the four motor commands, sends the IMU back.
- `ros_packages/rotors_simulator`: `rotors_gazebo_plugins`. Motor model, IMU, GPS,
  odometry, wind. The kopterworx xacro
  (`ardupilot_gazebo/models/kopterworx/urdf/kopterworx.urdf.xacro`) is built from the
  rotors macros in `rotors_description/urdf/component_snippets.xacro`.

The important part is how the two are coupled. `ArduPilotPlugin::ApplyMotorForces`
(around line 1024) has two code paths:

1. **Plugin drives the rotor joints itself.** This is the upstream behaviour. Each
   control channel has a velocity PID (`vel_p_gain`, `useForce`, `SetVelocity`, ...)
   that pushes the rotor joint to the commanded speed. Thrust is then whatever a lift
   plugin makes of that joint speed. No motor dynamics, no rotor drag, and the PID gains
   are just numbers someone picked.
2. **Plugin publishes motor speeds and rotors_simulator does the physics.** Set when the
   model gives the plugin a `controlTopicName`. The plugin then publishes a
   `mav_msgs/Actuators` message on `/<ns>/gazebo/command/motor_speed` and returns. The
   rotors `gazebo_motor_model` on each rotor subscribes to it and applies first order
   motor dynamics (`timeConstantUp/Down`), thrust from `motorConstant`, torque from
   `momentConstant`, rotor drag and rolling moment. It also reads the IMU from the rotors
   IMU plugin topic instead of the raw Gazebo sensor, so IMU noise is in the loop.
   Note the channel order in that publish is `0, 2, 1, 3`, that is the ArduPilot to
   rotors motor numbering swap.

We use path 2, see the `xacro:ardupilot` block in `kopterworx.urdf.xacro`
(`control_topic`, `imu_topic`, `thrust_multiplier`). That is why our sim hovers at a
realistic throttle and why `mavros/setpoint_raw/attitude` thrust maps to the real
aircraft. Path 1 is what you get if you drop rotors_simulator and use a stock model.

**The goal of the port is to keep path 2.** On the new Gazebo the equivalent is:

```
ArduPilotPlugin (ArduPilot/ardupilot_gazebo, gz-sim)
    -> gz.msgs.Actuators on /<model>/command/motor_speed
    -> gz::sim::systems::MulticopterMotorModel, one per rotor
```

`MulticopterMotorModel` is a port of the rotors `gazebo_motor_model` with the same
parameters. Upstream `iris_with_ardupilot` already uses this arrangement, check its
`model.sdf` for control channels of `<type>COMMAND</type>` with a `<cmd_topic>` and for
the `gz-sim-multicopter-motor-model-system` plugin instances. If that is what you find,
the coupling we have today exists upstream and the port is a model port, not a plugin
port. If upstream iris turns out to use the joint PID path, switch it to the motor model
path first and check that it still flies. Do not accept a kopterworx that flies on the
joint PID path, it will not match the real aircraft.

## Step 1: run upstream as is

Goal: prove the toolchain on a plain iris before touching our model.

The Dockerfile above already imported and built the workspace, so inside the container:

```bash
cd /root/ros2_ws && source install/setup.bash
ros2 launch ardupilot_gz_bringup iris_runway.launch.py
```

This brings up Gazebo with the iris, SITL (`sim_vehicle.py -f gazebo-iris --model JSON`)
and the micro-ROS agent for AP_DDS. Check:

```bash
ros2 topic list                       # expect /ap/pose/filtered, /ap/navsat, /ap/time ...
ros2 topic hz /ap/pose/filtered
ros2 service call /ap/arm_motors ardupilot_msgs/srv/ArmMotors "{arm: true}"
```

Also arm and take off from the MAVProxy console that sim_vehicle opens
(`mode guided`, `arm throttle`, `takeoff 3`). If the iris lifts, the Gazebo half is
fine. Write down the exact commits of ardupilot, ardupilot_gazebo, ardupilot_gz and
ros_gz that worked. That is your baseline.

Things that are known to bite here:

- The build pulls a lot. `colcon build` of ardupilot_gz plus micro-ROS takes a while
  the first time, and the repos file may pin a different ArduPilot branch than ours.
  Build upstream ArduPilot first, do not swap the fork in yet.
- If Gazebo starts but the model never arms, the ArduPilot plugin is not talking to
  SITL. Check that `sim_vehicle.py` was started with `--model JSON` and that the
  `fdm_addr`/`fdm_port_in` in the model SDF match (default 127.0.0.1, 9002).
- Sim time: ros_gz bridges `/clock`. Make sure nodes use `use_sim_time`.

## Step 2: decide the flight controller interface

This is the real decision of the investigation. The stack talks to ArduPilot over
MAVLink through mavros (attitude targets on `mavros/setpoint_raw/attitude`, odometry
from `mavros/global_position/local`, mode and arming services). There are two ways on
ROS 2:

**A. mavros2.** `ros-jazzy-mavros` exists and has the same topics. SITL exposes MAVLink
on UDP 14550 by default, so:

```bash
apt install -y ros-jazzy-mavros ros-jazzy-mavros-extras
ros2 run mavros install_geographiclib_datasets.sh
ros2 launch mavros apm.launch fcu_url:=udp://:14550@
ros2 topic hz /mavros/global_position/local
```

Then the test that matters for us: put SITL in GUIDED_NOGPS, arm, and publish an
`AttitudeTarget` at 50 Hz to `/mavros/setpoint_raw/attitude` from a tiny script. If the
vehicle responds the way it does on Noetic, the controllers port without changing the
interface. Keeps the 4.4.3 fork with its GUID_OPTIONS patch.

**B. AP_DDS.** Native ROS 2 topics from the autopilot, no mavros. Cleaner, but:

- needs ArduPilot 4.5 or newer, so the fork has to be rebased first;
- as of now the DDS interface has arm, mode, takeoff, velocity commands
  (`/ap/cmd_vel`) and global position commands, but check whether an attitude and
  thrust setpoint exists. If it does not, our cascade PID and MPC output has nowhere
  to go. Look at `libraries/AP_DDS/README.md` in the ArduPilot tree for the current
  topic list, it changes between releases.

Run both, write down what each one gives and at what rate. Expected outcome is A for
the port and B as a later option, but confirm it instead of assuming.

## Step 3: port the kopterworx model

Do this only after step 1 flies and you have confirmed the motor model path above.
The current model is `ardupilot_gazebo/models/kopterworx/urdf/*.xacro` built on
rotors_simulator macros, and rotors_simulator has no new Gazebo port. The plugins have
to be replaced one by one, the wiring stays the same.

Plugin mapping:

| Now (Classic, rotors) | New Gazebo | Note |
|---|---|---|
| librotors_gazebo_motor_model | gz-sim MulticopterMotorModel system | same params: motorConstant, momentConstant, timeConstantUp/Down, rotorDragCoefficient, maxRotVelocity |
| ArduPilotPlugin (classic fork) | ArduPilotPlugin from ArduPilot/ardupilot_gazebo | takes the IMU sensor name and per channel joint + topic |
| librotors_gazebo_imu_plugin | `<sensor type="imu">` + gz-sim-imu-system | noise in the sensor tag |
| librotors_gazebo_gps_plugin | `<sensor type="navsat">` + gz-sim-navsat-system | world needs `<spherical_coordinates>` |
| librotors_gazebo_magnetometer_plugin | `<sensor type="magnetometer">` | ArduPilot gets mag from its own SITL model anyway, check if needed |
| librotors_gazebo_odometry_plugin | OdometryPublisher system + ros_gz_bridge | this is the `/$UAV_NAMESPACE/odometry` ground truth |
| librotors_gazebo_multirotor_base_plugin | drop | only joint states and rotor visuals |
| librotors_gazebo_wind_plugin, bag_plugin | drop for now | |
| libgazebo_ros_camera | `<sensor type="camera">` + ros_gz_image | |
| velodyne_simulator | `<sensor type="gpu_lidar">` | built in, no plugin package needed |

How to do it in small steps:

1. Copy `iris_with_ardupilot` from ardupilot_gazebo/models to a `kopterworx` model
   in a new package (`kopterworx_gz_description` or similar, SDF not xacro to start).
   Fly it unchanged.
2. Swap the meshes and the four rotor positions and masses for the kopterworx ones.
   Take the numbers from `kopterworx_base.urdf.xacro` and `motor_parameters/`.
   Fly it.
3. Move motor constants over and load `config/kopterworx_v432.params` with
   `--add-param-file`. Fly it and compare hover throttle with the Noetic sim.
   The `thrust_multiplier` (667 today) will need retuning, note the new value.
4. Add the odometry publisher and bridge it to `nav_msgs/Odometry`. Compare against
   `mavros/global_position/local`.
5. Add IMU noise, then camera, then lidar, one at a time.

xacro still exists on ROS 2 (`ros-jazzy-xacro`) and `ros_gz_sim create` can spawn from
a URDF string, so the tilt rotor and manipulator variants can come back later. Do not
start there.

## Step 4: headless and CI

Once the model flies with a GUI, check it without one, since that is what CI needs:

```bash
gz sim -s -r --headless-rendering world.sdf    # server only
```

Sensors that render (camera, gpu_lidar) still need a render engine in headless mode.
On a machine without a GPU this means EGL software rendering, which is slow but works.
Time a full arm, takeoff, land cycle headless and note it. That number decides how CI
tests get structured.

## What to write down

Keep a `docs/ros2_sitl_findings.md` with:

- exact image, commits and apt versions of the working baseline;
- mavros2 vs AP_DDS: what works, rates, missing messages, chosen option and why;
- ArduPilot version needed and what that means for the fork
  (stay on 4.4.3 or rebase);
- model port status per step above, retuned constants;
- headless timing;
- anything that had to be patched, with a link to the upstream issue if one exists.

Time box the whole thing to two weeks. If step 1 does not fly in the first two days,
stop and write up what is blocking before continuing.
