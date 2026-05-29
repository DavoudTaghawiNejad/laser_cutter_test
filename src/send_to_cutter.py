#!/usr/bin/env python3
"""
grbl_streamer.py — Simple G-code streamer for GRBL / Marlin / Smoothieware.

Streams G-code over a serial port using the standard "send-response" protocol
(one line at a time, wait for `ok` / `error:` before sending the next).

Safety: use as a context manager. On exit — whether the job finishes normally,
raises an exception, or you Ctrl-C — `close()` runs the configured shutdown
commands (default: `M5` to turn the laser off) before releasing the port.

Configuration lives in `machine.yaml` (see the example shipped alongside this
file for the schema):

    with LaserStreamer('machine.yaml') as laser:
        laser.stream_from_file('job.gcode')

    with LaserStreamer('machine.yaml') as laser:
        laser.stream(gcode_str)

Requires `pyserial`, `PyYAML`, and `plac` (`pip3 install pyserial PyYAML plac`).
"""

import re
import time
from typing import Iterable, Iterator, Optional, Tuple
import serial
import yaml
from tqdm import tqdm as progress


class GrblError(Exception):
    """Raised when the controller returns an `error:` response."""

    def __init__(self, code: str, line: str):
        self.code = code
        self.line = line
        super().__init__(f"Controller returned {code!r} for line: {line!r}")


_COMMENT_RE = re.compile(r"\([^)]*\)")  # strip (...) inline G-code comments


class LaserStreamer:
    """Stream G-code to a GRBL-compatible controller, configured from YAML.

    Expected YAML keys:

        port: /dev/ttyUSB0
        baud: 115200
        timeout: 2.0
        wake_delay: 2.0
        homeing_timeout: 10.0

    Pass ``verbose=True`` to log each line number and controller response to
    stdout as the job streams.
    """

    DEFAULT_SHUTDOWN = ("M5",)  # laser off

    def __init__(self, config_path: str, verbose: bool = False):
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
        if not isinstance(cfg, dict):
            raise ValueError(
                f"{config_path}: top-level YAML must be a mapping, got {type(cfg).__name__}"
            )
        if "port" not in cfg:
            raise ValueError(f"{config_path}: missing required key 'port'")

        self.port: str = cfg["port"]
        self.baud: int = cfg.get("baud", 115200)
        self.timeout: float = cfg.get("timeout", 2.0)
        self.wake_delay: float = cfg.get("wake_delay", 2.0)
        self.homeing_timeout: float = cfg.get("homeing_timeout", 10.0)
        self.verbose: bool = verbose
        self._serial: Optional[serial.Serial] = None
        print(f"Loaded machine config from {config_path}")

    # --- Lifecycle --------------------------------------------------------

    def open(self) -> "LaserStreamer":
        """Open the serial port and wake the controller."""
        self._serial = serial.Serial(self.port, self.baud, timeout=self.timeout)
        self._serial.write(b"\r\n\r\n")
        time.sleep(self.wake_delay)
        self._serial.reset_input_buffer()
        print(f"Connected to {self.port} @ {self.baud}")
        return self

    def close(self) -> None:
        """Run safe-shutdown commands, then close the port. Always safe to call."""
        if self._serial is None:
            return
        try:
            try:
                self.send('M5')
                self.send('G0 X0 Y0')
            except Exception as e:
                self._serial.write(b"\x18")   # GRBL soft reset (Ctrl-X)
                print("Please hit emergency off")
                print(f"WARNING: safe-shutdown command failed: {e}")
        finally:
            self._serial.close()

    def __enter__(self) -> "LaserStreamer":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False  # never swallow exceptions

    def _wait_for_buffer(self) -> None:
        while True:
            self._serial.write(b"?")
            self._serial.flush()
            status = self._serial.readline().decode("ascii", errors="replace").strip()
            m = re.search(r"Bf:\d+,(\d+)", status)
            if m and int(m.group(1)) >= 512:
                print('.', end='')
                return
            time.sleep(0.05)

    def send(self, command: str, line_number: Optional[int] = None) -> str:
        """Send one G-code command and return the controller's ``ok``/``error:`` line.

        Any informational lines the controller sends *before* the ``ok``/``error:``
        terminator (e.g. the firmware string returned by ``$I``) are collected and,
        when ``self.verbose`` is ``True``, printed individually before the final
        status line.  The return value is always the terminating ``ok``/``error:``
        string, preserving backwards compatibility.

        Args:
            command:     The G-code command string to send.
            line_number: Optional 1-based line number used by :meth:`stream` for
                         verbose output.  Has no effect when ``self.verbose`` is
                         ``False``.
        """
        if self.verbose:
            print(f"[{line_number + 1}]  >> {command.strip()!r} ", end='')
        self._wait_for_buffer()
        command = command.split(';')[0].strip()
        if command.upper().startswith(('$H', 'M0', 'G92')):
            self._serial.timeout = self.homeing_timeout
        else:
            self._serial.timeout = self.timeout
        try:
            for _ in range(2):
                self._serial.write((command.strip() + "\n").encode("ascii"))
                self._serial.flush()
                info_lines: list[str] = []
                while True:
                    raw = self._serial.readline()
                    if not raw:
                        break
                    resp = raw.decode("ascii", errors="replace").strip()
                    if not resp:
                        continue
                    if resp.startswith("ok") or resp.startswith("error"):
                        if self.verbose:
                            for info in info_lines:
                                print()
                                print(info, end='')
                            print(f" ->  {resp!r}")
                        if resp.startswith("ok"):
                            return resp
                        else:
                            raise GrblError(resp, line_number + 1)
                    info_lines.append(resp)

            raise TimeoutError(f"No response from controller for {command!r} in {line_number + 1}")
        except (Exception, KeyboardInterrupt):
            self._serial.write(("M5\n").encode("ascii"))
            self._serial.flush()
            print("M5 sent (LaserStreamer.send)")
            raise

    def stream(self, gcode: str):
        """Stream a multi-line G-code string.

        Splits `gcode` on newlines and sends each line one-by-one, waiting for
        the controller's `ok` after each. Blank lines and comments (`;` line
        comments and `(...)` inline comments) are stripped. Raises `GrblError`
        immediately on any `error:` response.

        When ``self.verbose`` is ``True``, each sent line is logged to stdout
        with its 1-based line number (counting only non-blank, non-comment
        lines) and the controller's response.

        For a file:  ``laser.stream(open('job.gcode').read())``.
        """
        for i, raw in enumerate(progress(gcode.splitlines())):
            line = self._clean(raw)
            if not line:
                continue
            self.send(line, line_number=i)


    def stream_from_file(self, filename):
        with open(filename) as f:
            gcode = f.read()
        self.stream(gcode)

    @staticmethod
    def _clean(line: str) -> str:
        line = _COMMENT_RE.sub("", line).strip()
        if not line or line.startswith(";"):
            return ""
        return line


# --- CLI ------------------------------------------------------------------

def _cli(
    gcode_file: "Path to .gcode file",
    config: "Path to machine YAML config" = "machine.yaml",
    verbose: ("Print each line number and controller response", "flag", "v") = False,
):
    """Stream a G-code file to a GRBL-compatible controller."""
    with LaserStreamer(config, verbose=verbose) as laser_cutter:
        laser_cutter.stream_from_file(gcode_file)

if __name__ == "__main__":
    import plac
    plac.call(_cli)
