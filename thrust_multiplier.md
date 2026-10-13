# thrust_multiplier: what it is, whether 667 is right, what to change

Written 2026-10-05. Fix is tracked in Jira: USOIT-36, subtask of USOIT-11.

## Short version

- `thrust_multiplier` is not a thrust factor and not a tuning knob. It is the **rotor
  speed at full throttle in rad/s**. The Gazebo plugin needs it to turn ArduPilot's PWM
  into the rotor speed the motor model expects. It cannot be removed.
- Its value, 667, is the same number as the motor model's `max_rot_velocity`. Today the
  two are typed separately. That is the bad practice: one physical quantity, two places,
  a misleading name and a stale comment.
- The conversion works exactly as the code says (measured).
- Whether 667 is the right maximum for the real aircraft is open. The simulated vehicle
  hovers at 22 % less throttle than the value the real aircraft learned. One number from
  the real aircraft closes this.
- It never has to change for a ROS, Gazebo or firmware version. Only when the modelled
  motor, propeller or battery changes.

## What it is

```
ArduPilot SITL                Gazebo plugin (ArduPilotPlugin)             motor model (one per rotor)
motor output, PWM 1000..2000  raw = (pwm - servo_min)/(servo_max - servo_min)   ref = min(cmd, maxRotVelocity)
                       ---->  cmd = multiplier * (raw + offset)          ---->  thrust = motorConstant * speed^2
                              cmd is a rotor speed in rad/s
```

- Plugin code: `ArduPilotPlugin.cc`, `UpdateMotorCommands` (Harmonic, line 1708) and the
  same expression in the Classic fork (line 1163).
- Motor model: `gazebo_motor_model.cpp:131` on Classic (rotors_simulator),
  `MulticopterMotorModel.cc:537` on gz-sim 8. Both clamp the reference to
  `maxRotVelocity`.
- `<multiplier>` is the plugin's name. Every upstream model has one (iris: 838).
  `thrust_multiplier` is our name: an argument of the `ardupilot` xacro macro in
  `larics/ardupilot_gazebo`, `models/util/multirotor_base.urdf.xacro`, added in a4d3060
  (2020-04-24).
- Not to be confused with mavros `thrust_scaling`, which scales the thrust field of an
  AttitudeTarget inside mavros and has nothing to do with the model.

## Where 667 comes from

| quantity | value | source |
|---|---|---|
| `motor_constant` | 2.440724623743665e-04 N s^2 | reproducible: `motor_parameters/get_thrust_and_torque_k.m` on `22x8.mat` (APC 22x8 static data) gives 2.440724618e-04 |
| `moment_constant` | 0.044148079282817 m | same script, gives 0.0441480777 |
| `max_rot_velocity` | 667 rad/s (6370 rpm) | **not derived anywhere in the repo**, no motor, ESC or battery data |
| `thrust_multiplier` | 667 | copy of `max_rot_velocity` |

- Multiplier and `max_rot_velocity` are the same number in kopterworx (667/667), broli
  (667/667), hawk (628.318/628.318) and ardrone (1475/1475). Bebop is the one model
  where they drifted apart (1000 vs 1475).
- Both went from 600 to 667 in one commit, 7a39b49 (2022-12-05), together with the
  switch of the propeller table from APC 22x11E to 22x8.
- What 667 implies: 108.6 N (11.07 kgf) per motor at full throttle, thrust to weight
  4.9 for the 9 kg model. With 600 it is 87.9 N and 4.0.
- Detail on the script: it uses the quadratic coefficient of a full second order fit.
  A pure k w^2 fit of the same table gives 2.398e-4, 1.7 % lower. Not significant here.

## Measurements

PoC session `kopterworx_flat`, headless, clean SITL storage, 50 s hover at 3 m, ArduPilot
master, parameters `kopterworx_v432.params`. Model mass 9.05 kg (9 kg body, rotors,
sensor links), weight 88.78 N.

| multiplier | hover PWM (normalised) | rotor speed published by the plugin | 4 k w^2 | learned `MOT_THST_HOVER` |
|---|---|---|---|---|
| 667 (repo) | 1452 (0.452) | 301.48 rad/s | 88.74 N | 0.225 |
| 602 (scratch copy of the model) | 1501 (0.501) | 301.60 rad/s | 88.81 N | 0.275 |
| 600 (scratch copy, 2026-10-13) | 1502 (0.502) | 301.2 rad/s | 88.57 N | 0.2775 |

- 0.452 x 667 = 301.5 and 0.501 x 602 = 301.6. The plugin does what the code says.
- Thrust equals weight to 0.05 %. The motor model does what its constants say.
- The hover rotor speed is the same in both runs. The multiplier only decides which PWM
  produces it.
- `kopterworx_v432.params` carries `MOT_THST_HOVER` 0.290, learned on the real
  aircraft. With 667 the simulation learns 0.225, 22 % lower. With 602 it learns 0.275,
  5 % lower.

So the simulated vehicle is stronger, or lighter, than the real one. Three possible
causes, not separable from the repo:

1. the real maximum rotor speed is lower than 667 rad/s (around 600 would fit),
2. the real take-off mass is above 9 kg,
3. the real thrust is below the APC static table.

Resolved 2026-10-13, see "Part B result" below: the take-off mass is 9 kg, cause 1.

## What it affects

- **Hover throttle.** ArduPilot learns it (`MOT_HOVER_LEARN 2`), so the vehicle flies
  with either value.
- **Gain of the plant the rate loops see.** Thrust per unit of command at hover is 97.9 N
  at 667 and 88.4 N at 602, 10 % apart. The rate gains in the parameter file were tuned
  on the real aircraft.
- **Thrust headroom.** 4.9 vs 4.0.
- **Not what the stack sends.** `kopterworx_v432.params` has `GUID_OPTIONS 0`. ArduPilot
  then reads the thrust of an AttitudeTarget as a climb rate, 0.5 means hold altitude
  (`GCS_MAVLink_Copter.cpp`, same on master and Larics-4.4.3). The multiplier does not
  move that. The xacro comment "Value is tuned in order for
  mavros/setpoint_raw/attitude/thrust to reflect real-world behavior" belongs to the
  older parameter sets with `GUID_OPTIONS 8` (thrust as thrust,
  `kopterworx_red_v41_thrust_compassless.params`), where the mavros thrust went straight
  to the motors. For the current parameters it is stale.

## When it has to change

- Only when the powertrain of the modelled aircraft changes: motor, propeller, battery
  voltage. Then together with `max_rot_velocity`, because it is the same quantity.
- Not for ROS 1 to ROS 2, Classic to Harmonic, or a firmware version. The port carried
  it over unchanged and the hover point matches the analytic value.
- If the two numbers diverge:
  - multiplier above `max_rot_velocity`: the motor model clamps, the top of the throttle
    range does nothing, ArduPilot does not know it is saturated;
  - multiplier below: the maximum is never reached and `max_rot_velocity` means nothing.

## What is wrong today

1. One physical quantity is typed in two places (`max_rot_velocity` in the base xacro,
   `thrust_multiplier` at the macro call). Bebop shows they drift.
2. The name says thrust. It is a rotor speed. It also gets mixed up with mavros
   `thrust_scaling`.
3. The comment says "tuned", which invites using it as a fudge factor. The right levers
   for matching the real aircraft are the physical values: mass, motor constant, maximum
   rotor speed.
4. The value 667 has no recorded source.
5. USOIT-32 used to plan settling the value by comparing with the Noetic simulation.
   Noetic uses the same numbers, so that comparison checks the port, not the value.
   USOIT-32 was rewritten on 2026-10-08 to do exactly that: same hover throttle as Noetic.

## Fix

In `ardupilot_gazebo_description` (the ROS 2 package in uav_ros_simulation; Noetic
branches stay untouched):

1. The `ardupilot` macro takes `max_rot_velocity` instead of `thrust_multiplier`, and
   the kopterworx xacro passes `${max_rot_velocity}`, the property that already feeds
   the four motor models. One number, one place.
2. Comments say what it is: rotor speed at full throttle, rad/s.
3. The value of `max_rot_velocity` is checked against the real aircraft and its source
   is written next to it.

Step 1 and 2 change no behaviour. Step 3 needs one of these from the real kopterworx:

- measured maximum rpm of the motor with the 22x8 propeller at full battery, or
- mean PWM of the four motors in a steady hover, from a flight log, with the take-off
  mass of that flight.

From the hover log: `max_rot_velocity = sqrt(m * 9.81 / (4 * motor_constant)) / p`, with
`p = (pwm - 1000) / 1000`. Example: 9 kg and 1500 give 601 rad/s.

The PoC generator `ros2_sitl/kopterworx_gz/scripts/gen_model.py` has the same two
constants (`MAX_ROT_VELOCITY`, `THRUST_MULTIPLIER`, both 667). It is reference material
and was left as it is.

## Part B result (2026-10-13)

Input: real take-off mass 9 kg (Lovro, 2026-10-13). No flight log is needed: the learned
`MOT_THST_HOVER` 0.290 in `kopterworx_v432.params` is the hover output in disguise. Run
back through the aircraft's own curve (`MOT_THST_EXPO` 0.65, `MOT_SPIN_MIN` 0.13,
`MOT_SPIN_MAX` 0.95; `AP_Motors_Thrust_Linearization.cpp`) it gives a motor output of
0.500, PWM 1500, at full battery. The same inversion reproduces the two measured rows
above within 1 % (0.225 gives 1440 vs 1452 measured, 0.275 gives 1486 vs 1501).

Candidate by the formula in the ticket: `sqrt(9 * 9.81 / (4 k)) / 0.500` = 602 (604 with
the 9.05 kg model mass). Outside the 634 to 700 band, so the value changes.

Measured with 600 (the eight `667.0` in `model.sdf` set to `600.0`, clean storage, 50 s
hover at 3 m, headless):

| | measured | real aircraft |
|---|---|---|
| mean normalised output | 0.502 (PWM 1502) | 0.500 (PWM 1500) |
| rotor speed published by the plugin | 301.2 rad/s (0.502 x 600; gate 301 within 5) | |
| learned `MOT_THST_HOVER` | 0.2775 | 0.290 |

Why the learned value is still 4 % under 0.290 although the PWM matches: ArduPilot
compensates the throttle for air density (`Thrust_Linearization::get_compensation_gain`,
`AP_MOTORS_DENSITY_COMP`), so the stored hover value is for sea level. SITL flies at
CMAC, 584 m above sea level (`Tools/autotest/locations.txt`), density ratio 0.945. The
hover thrust at the site is 0.2775 / 0.945 = 0.294, the same as the 0.293 the curve gives
for PWM 1502. The real aircraft learned 0.290 near sea level. With 600 the simulated
hover matches the real one within 1.5 %; what is left in the stored parameter is the
SITL home altitude, not the model. Battery voltage plays no part: SITL reports no
voltage on `BATT_VOLT_PIN` 14 (a Cube pin), and ArduPilot then keeps `lift_max` at 1.

Decision: `max_rot_velocity` 600. The candidate is 602; 0.3 % is below the repeatability
of the learned value (0.275 at 602, 0.2775 at 600). Thrust to weight becomes 4.0, 87.9 N
per motor at full throttle.

Pitfall found on the way: the container runs on the host network with Jazzy's default
`ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`, so a Jazzy simulation on another machine in the
same LAN appears on the same topics. The first run mixed two vehicles: `hover_test.py`
saw one at 3 m with PWM 1452 and one on the ground, alternating, and the takeoff command
was refused. `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` fixes it; it is now in
`ros2_sitl_env.sh`.

## Reproduce

Inside the container (`ros2_sitl/docker_run.sh -d`, then `ros2_sitl/docker_run.sh`):

```bash
# clean SITL storage, otherwise the learned hover value of the last run is loaded
mv /root/ros2_sitl/logs/sitl_kopterworx/eeprom.bin /tmp/ 2>/dev/null
cd /root/ros2_sitl/startup/kopterworx_flat && GUI=false HEADLESS=true ./start.sh --no-attach
source /root/ros2_sitl/startup/shell_helpers.sh && waitForArmable
python3 /root/ros2_sitl/scripts/hover_test.py --hover-s 50 &     # prints the mean normalised motor output
sleep 50; gz topic -e -n 1 -t /kopterworx/command/motor_speed    # rotor speed the plugin publishes, rad/s
wait
ros2 service call /mavros/param/pull mavros_msgs/srv/ParamPull "{force_pull: true}"
ros2 param get /mavros/param MOT_THST_HOVER                      # learned value, saved at disarm
/root/ros2_sitl/kill_sim.sh
```

Motor constants: load `motor_parameters/22x8.mat` from `larics/ardupilot_gazebo`
(`rpm`, `thrust_lbf`, `torque_lbf`), convert to rad/s, N and Nm, then
`polyfit(rad_s, thrust, 2)[0]` and `polyfit(thrust, torque, 1)[0]`.

## Jira

USOIT-36 "5a. Kopterworx model: replace thrust_multiplier with max_rot_velocity, check the
value against the real aircraft", subtask of USOIT-11. Part A is the rename (no
behaviour change), part B the value: settled 2026-10-13 at 600, Toni applies it. It overrides
the "multiplier 667" wording in USOIT-25 item 4. USOIT-32 no longer mentions the value.
