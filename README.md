
# A script that generates a gcode matrix with different power, speed, and pass number combinations to find optimal laser cutter setting.


A script that generates a gcode matrix with different power, speed, and pass number combinations to find optimal laser cutter setting.

This generates gcode to print the gcode object in 'job.yaml' 200 times at different power, speed, and number of passes settings::

    python generate_test_gcode.py 50 400 100 10000 1 4 --laser --to-cutter

&nbsp;

    python generate_test_gcode.py power_min power_max speed_min speed_max min_passes max_passes [--laser switches on] [--to_cutter sends directly to cutter]

See README.md how to change the object that is cut out at different speed, power, and pass numbers.
Edit machine.yaml to use 'to_cutter' command.

The object's M4 commands must be changed to 'M4 S{POWER}'. The F value of all speed commands (G1 - G5) must be changed:
from F1234 to F{speed}. For example, 'G1 X1.174 Y2.176 F1500' becomes 'G1 X1.174 Y2.176 F{speed}'.

generated gcode in fence.gcode (which only moves around the cutting aread) and output.gcode which lasers.

The resulting gcode prints, but DOES NOT DISPLAY CORRECTLY IN GCODE VIEWERS.
The gcode viewer at https://nraynaud.github.io/webgcode/ works.

positional arguments:
  power_min             Smallest power setting (percent, integer)
  power_max             Power increments
  speed_min             Smallest speed setting
  speed_max             Speed increments
  min_passes            Smallest number of passes
  max_passes            Highest number of passes

options:
  -h, --help            show this help message and exit
  -p, --power-steps None
                        Optional: Number of power steps
  -s, --speed-steps None
                        Optional: Number of speed steps
  -sw, --sheet-width 1  Optional: Fraction of sheet width defined in job yaml
  -sh, --sheet-height 1
                        Optional: Fraction of sheet hight defined in job yaml
  -j, --job job         job.yaml contains objects and size, defaults to job for job.yaml, see example.yaml
  -o, --output output   output filename, defaults to 'output.gcode'
  -l, --laser           Switch laser on
  -c, --to-cutter       Operates the lasercutter specfied in machine.yaml directly
  -t, --transpose       Reverses power and speed axis

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
