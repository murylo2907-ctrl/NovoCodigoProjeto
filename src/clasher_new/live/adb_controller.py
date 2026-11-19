"""ADB driver: turn a (slot, y, x) decision into a swipe on the emulator screen."""
import re
import subprocess


class ADBController:
    def __init__(self, serial=None, config=None):
        config = config or {}
        self.serial = serial or config.get("serial")
        self.arena = config.get("arena", {"left": 0.0, "right": 1.0, "top": 0.115, "bottom": 0.845})
        self.hand_y = config.get("hand_y", 0.905)
        self.hand_x = config.get("hand_x", [0.125, 0.375, 0.625, 0.875])
        self.swipe_ms = int(config.get("swipe_ms", 120))
        self.size = self.screen_size()

    def _run(self, *args, timeout=10):
        command = ["adb"] + (["-s", self.serial] if self.serial else []) + [str(arg) for arg in args]
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)

    def screen_size(self):
        output = self._run("shell", "wm", "size").stdout
        match = re.search(r"(\d+)x(\d+)", output)
        if not match:
            raise RuntimeError("could not read the screen size; is adb connected? " + output.strip())
        return int(match.group(1)), int(match.group(2))

    def arena_point(self, y, x):
        """Tile (y, x) in the simulator's view (y=0 is our side) to screen pixels."""
        width, height = self.size
        left = self.arena["left"] * width
        right = self.arena["right"] * width
        top = self.arena["top"] * height
        bottom = self.arena["bottom"] * height
        screen_x = left + (x + 0.5) / 18 * (right - left)
        screen_y = bottom - (y + 0.5) / 32 * (bottom - top)
        return int(round(screen_x)), int(round(screen_y))

    def hand_point(self, slot):
        width, height = self.size
        return int(round(self.hand_x[slot] * width)), int(round(self.hand_y * height))

    def drag(self, start, end):
        result = self._run("shell", "input", "swipe", start[0], start[1], end[0], end[1], self.swipe_ms)
        if result.returncode != 0:
            raise RuntimeError("adb swipe failed: " + result.stderr.strip())

    def play_card(self, slot, y, x):
        """Hold the hand card and drop it on tile (y, x); returns the screen point."""
        if not 0 <= slot < 4:
            return None
        target = self.arena_point(y, x)
        self.drag(self.hand_point(slot), target)
        return target
