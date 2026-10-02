#!/usr/bin/env python3
"""Time one arm -> takeoff -> land -> disarm cycle, wall clock and sim clock.

Prints the wall seconds and sim seconds (from /clock) for each phase and the ratio,
plus the Gazebo real time factor sampled from the odometry/clock. Exit 0 on success.
  python3 cycle_test.py [--alt 3] [--hover-s 5]
"""
import argparse, sys, time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from rosgraph_msgs.msg import Clock
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, CommandTOL, SetMode
from arming import arm_with_retry


class Cycle(Node):
    def __init__(self):
        super().__init__("cycle_test"); self.state=None; self.pose=None; self.clock=None
        be = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(State, "/mavros/state", lambda m: setattr(self, "state", m), 10)
        self.create_subscription(PoseStamped, "/mavros/local_position/pose", lambda m: setattr(self, "pose", m), be)
        self.create_subscription(Clock, "/clock", lambda m: setattr(self, "clock", m), be)
        self.mode_cli = self.create_client(SetMode, "/mavros/set_mode")
        self.arm_cli = self.create_client(CommandBool, "/mavros/cmd/arming")
        self.tol_cli = self.create_client(CommandTOL, "/mavros/cmd/takeoff")

    def sim(self):
        return self.clock.clock.sec + self.clock.clock.nanosec * 1e-9 if self.clock else float("nan")

    def wait(self, cond, timeout, what):
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.02)
            if cond(): return True
        print(f"TIMEOUT waiting for {what}"); return False

    def call(self, cli, req, what):
        cli.wait_for_service(timeout_sec=5.0)
        f = cli.call_async(req); rclpy.spin_until_future_complete(self, f, timeout_sec=5.0)
        r = f.result(); print(f"{what}: {r}"); return r

    def run(self, a):
        if not self.wait(lambda: self.state and self.state.connected and self.pose and self.clock, 60, "FCU/pose/clock"): return 1
        marks = []
        def mark(name): marks.append((name, time.time(), self.sim())); print(f"[{name}] wall={marks[-1][1]-marks[0][1]:6.1f}s sim={marks[-1][2]-marks[0][2]:6.1f}s", flush=True)
        mark("start")
        self.call(self.mode_cli, SetMode.Request(custom_mode="GUIDED"), "GUIDED")
        if not arm_with_retry(self, self.arm_cli, lambda: self.state.armed): return 1
        mark("armed")
        self.call(self.tol_cli, CommandTOL.Request(altitude=float(a.alt)), f"takeoff {a.alt}")
        if not self.wait(lambda: self.pose.pose.position.z > a.alt - 0.2, 60, "altitude"): return 1
        mark("at_alt")
        if not self.wait(lambda: False, a.hover_s, "hover") and False: pass
        mark("hover_done")
        self.call(self.mode_cli, SetMode.Request(custom_mode="LAND"), "LAND")
        if not self.wait(lambda: not self.state.armed, 90, "disarm after land"): return 1
        mark("disarmed")
        w = marks[-1][1] - marks[0][1]; s = marks[-1][2] - marks[0][2]
        print(f"CYCLE wall={w:.1f}s sim={s:.1f}s sim/wall={s / w:.2f}", flush=True)
        return 0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--alt", type=float, default=3.0); ap.add_argument("--hover-s", type=float, default=5.0)
    a = ap.parse_args(); rclpy.init(); n = Cycle()
    try: rc = n.run(a)
    finally: n.destroy_node(); rclpy.shutdown()
    sys.exit(rc)

if __name__ == "__main__": main()
