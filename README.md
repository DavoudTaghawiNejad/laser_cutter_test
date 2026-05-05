
# A script that generates a gcode matrix with different power, speed, and pass number combinations to find optimal laser cutter setting.


This generates gcode to print the gcode object in 'job.yaml' 200 times at different power, speed, and number of passes settings::

    python generate_test_gcode.py 5 5 7 500 250 10 1 4 --laser --to-cutter

&nbsp;

    python generate_test_gcode.py  power_start  power_stepsize  power_steps  speed_start  speed_stepsize  speed_steps  min_passes  max_passes [--laser switches on] [--to-cutter sends directly to cutter]

'job.yaml' contains the object's gcode and sizes of the object and the sheet as well as the power and
speed with which the axis is engraved. Generate the gcode for the object you want to test in your favorite
gcode generator (lightburn, rayforge ...). Make sure it is close to the origin. Note the width
and height. Copy the object to 'job.yaml' and edit M5 and G1, to G5 commands as follows:

The object's M4 commands must be changed to 'M4 S{POWER}'. The F value of all speed commands (G1 - G5) must be changed:
from F1234 to F{speed}. For example, 'G1 X1.174 Y2.176 F1500' becomes 'G1 X1.174 Y2.176 F{speed}'.

See 'example.yaml' for reference, README.md for additional help.

generated gcode in fence.gcode (which only moves around the cutting aread) and output.gcode which lasers,
if mock option is not enabled.


The resulting gcode prints, but DOES NOT DISPLAY CORRECTLY IN GCODE VIEWERS.

positional arguments:
  - `power_start` -    Smallest power setting (percent, integer)
  - `power_stepsize` - Power increments
  - `power_steps` -    Number of power steps
  - `speed_start` -    Smallest speed setting
  - `speed_stepsize` - Speed increments
  - `speed_steps` -    Number of speed steps
  - `min_passes` -     Smallest number of passes
  - `max_passes` -     Highest number of passes

options:
  -h, --help              show this help message and exit
  -j, --job job           job.yaml contains objects and size, defaults to job for job.yaml, see example.yaml
  -o, --output filename   job.yaml contains objects and size, defaults to job for job.yaml, see example.yaml
  -l, --laser             Switch laser on
  -t, --to-cutter         Operates the lasercutter specfied in machine.yaml directly

# In the following example two squares are printed at various speeds and power and pass settings

Example two_tiny_squares.yaml::



    object_width: 5
    object_height: 10
    sheet_width: 195
    sheet_height: 285
    axes_power: 10
    axes_speed: 5000


    object: |
        ; Rounded square #1 (top)
        G0 X0.145 Y2.17
        M4 S{power}
        G1 X1.174 Y2.176 F{speed}
        G3 X1.215 Y2.424 I-0.151 J0.152 F{speed}
        G1 X1.145 Y2.47 F{speed}
        G1 X0.117 Y2.464 F{speed}
        G3 X0.145 Y2.17 I0.108 J-0.138 F{speed}
        M5                  ; Laser OFF

        ; Rounded square #2
        G0 Y1.67
        M4 S{power}
        G2 X0.117 Y1.964 I0.079 J0.156 F{speed}
        G1 X1.145 Y1.97 F{speed}
        G1 X1.215 Y1.924 F{speed}
        G2 X1.174 Y1.676 I-0.192 J-0.096 F{speed}
        G1 X0.145 Y1.67 F{speed}
        M5


With the following command line code::

    python generate_test_gcode.py 5 5 7 500 250 10 1 4 --job two_tiny_squares
