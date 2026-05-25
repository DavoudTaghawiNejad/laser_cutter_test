import math
from pprint import pprint
import yaml
from types import SimpleNamespace
import plac
from send_to_cutter import LaserStreamer
from helper import rename_digit_dict


class VirtualMachine:
    def __init__(self, job, to_cutter, sheet_width, sheet_height, output_filename='output'):
        with open('snippets.yaml') as snippets_file:
            self.snippets = SimpleNamespace(**yaml.safe_load(snippets_file))
        with open('digits.yaml') as digits_file:
            self.digits = rename_digit_dict(yaml.safe_load(digits_file))
        self.output_filename = output_filename
        self.axis_width = 5 * (self.digits['letter_width'] + self.digits['distance_between_letters']) + self.digits['distance_between_letters']
        self.width = max(job.object_width, 2 * (self.digits['letter_width']) + self.digits['distance_between_letters'] + self.digits['distance_between_numbers'])
        self.height = max(job.object_height, self.digits['letter_height'])
        self.lines = int(sheet_width / self.width)
        self.columns = int(sheet_height / self.height)
        self.axes_writing = [['' for _ in range(self.lines)] for __ in range(self.columns)]
        self.axis_height = 2 * self.digits['letter_height']
        self.axes_power = job.axes_power
        self.axes_speed = job.axes_speed
        self.x = 0
        self.y = 0
        self.object = job.object
        self.gcode = ''
        self.gcode += self.snippets.start
        self.to_cutter = to_cutter
        self.hard_column_offset = 0
        self.hard_row_offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *arg):
        self.save()
        if self.to_cutter:
            with LaserStreamer('machine.yaml') as laser_cutter:
                laser_cutter.stream(self.gcode + self.snippets.end)

    def save(self, output_filename=None):
        if output_filename is None:
            output_filename = self.output_filename
        with open(f'{output_filename}.gcode','w') as outputfile:
            outputfile.write(self.gcode + self.snippets.end)
        print(f'{output_filename}.yaml saved')

    def position(self, row=None, column=None):
        if column is not None:
            x = self.width * column + self.hard_column_offset
        else:
            x = self.x
        if row is not None:
            y = self.height * row + self.hard_row_offset
        else:
            y = self.y
        self.x = x
        self.y = y
        self.gcode += self.snippets.set_origin.format(x=x, y=y) + '\n'

    def set_machine_origin_to_graph_origin(self):
        self.hard_column_offset = self.axis_width
        self.hard_row_offset = self.axis_height

    def draw_at(self, row, column, power, speed, num_passes):
        self.position(row, column)
        self.gcode += '\n'.join([self.object.format(power=power, speed=speed) for _ in range(num_passes)]) + '\nM5\n'

    def mark_fence_posts(self, row, column):
        self.gcode += self.snippets.fence.format(x=self.width * (column + 1) + self.axis_width, y=self.height * (row + 1) + self.axis_height, speed=250) + '\n'

    def write_at(self, row, column, number, prepend=None):
        self.position(0, 0)
        self.gcode += 'G91\n'

        if prepend is None:
            self.axes_writing[row + 1][column] = f'{int(number)}'
            nstring = str(number)
            self.gcode += f'G0 X0 Y{self.axis_height + row * self.height}\n'
        else:
            self.axes_writing[row][column + 1] = f'{prepend}-{int(number//10)}'
            nstring = str(number // 10)
            y = self.axis_height / 2
            nstring = f'{prepend}d{nstring}'  # letter d go down and left
            self.gcode += f'G0 X{self.axis_width + column * self.width} Y{y}\n'

        for digit in nstring:
            self.gcode += self.digits[f'{digit}'].format(power=self.axes_power, speed=self.axes_speed) + '\n'
            self.gcode += self.digits['space'].format(space=self.digits['distance_between_letters']) + '\n'
        self.gcode += 'G90\n'

    def remove_power_on_gcode(self):
        gcode = [line
                 for line in self.gcode.split('\n')
                 if not line[0:2].strip().upper() in ['M3', 'M4', 'M5', 'M10', 'M11', 'M42']]
        self.gcode = ('\n').join(gcode)

    def print_axes_writing(self):
        for line in reversed(self.axes_writing):
            for cell in line:
                try:
                    print(f'{cell:<6}', end='')
                except (TypeError, ValueError):
                    print('.', end='')
            print()

@plac.pos('power_min', type=float, help="Smallest power setting (percent, accepts one digit after decimal point)")
@plac.pos('power_max', type=float, help="Highest power setting (percent, accepts one digit after decimal point)")
@plac.pos('speed_min', type=int, help="Smallest speed setting")
@plac.pos('speed_max', type=int, help="Highest speed setting")
@plac.pos('min_passes', type=int, help="Smallest number of passes")
@plac.pos('max_passes',type=int, help="Highest number of passes")
@plac.opt('job', type=str, help="job.yaml contains objects and size, defaults to job for job.yaml, see example.yaml")
@plac.opt('output', type=str, help="output filename, defaults to 'output.gcode'")
@plac.flg('laser', help="Switch laser on")
@plac.flg('to_cutter', abbrev='c', help="Operates the lasercutter specfied in machine.yaml directly")
@plac.opt('power_steps', type=int, help="Optional: Number of power steps")
@plac.opt('speed_steps', type=int, help="Optional: Number of speed steps")
@plac.opt('sheet_width', abbrev='sw', type=float, help="Optional: Fraction of sheet width defined in job yaml")
@plac.opt('sheet_height', abbrev='sh', type=float, help="Optional: Fraction of sheet hight defined in job yaml")
@plac.flg('fence_only', help="Only mark the fence")
def generate(power_min, power_max, speed_min, speed_max, min_passes, max_passes,
             power_steps=None, speed_steps=None, sheet_width=1, sheet_height=1,
             job='job', output='output', laser=False, to_cutter=False, fence_only=False):
    """ A script that generates a gcode matrix with different power, speed, and pass number combinations to find optimal laser cutter setting.


        This generates gcode to print the gcode object in 'job.yaml' 200 times at different power, speed, and number of passes settings::

            python generate_test_gcode.py 50 400 100 10000 1 4 --laser --to-cutter

            python generate_test_gcode.py power_min power_max speed_min speed_max min_passes max_passes [--laser switches on] [--to_cutter sends directly to cutter]

        See README.md how to change the object that is cut out at different speed, power, and pass numbers.
        Edit machine.yaml to use 'to_cutter' command.

        The object's M4 commands must be changed to 'M4 S{POWER}'. The F value of all speed commands (G1 - G5) must be changed:
        from F1234 to F{speed}. For example, 'G1 X1.174 Y2.176 F1500' becomes 'G1 X1.174 Y2.176 F{speed}'.

        generated gcode in fence.gcode (which only moves around the cutting aread) and output.gcode which lasers.

        The resulting gcode prints, but DOES NOT DISPLAY CORRECTLY IN GCODE VIEWERS.
        The gcode viewer at https://nraynaud.github.io/webgcode/ works.

    """
    power_max = int(power_max * 10)
    power_min = int(power_min * 10)
    with open('job.yaml') as job_file:
        job = SimpleNamespace(**yaml.safe_load(job_file))
    if sheet_width <= 1:
        sheet_width = job.sheet_width * sheet_width
    if sheet_height <= 1:
        sheet_height = job.sheet_height * sheet_height

    with VirtualMachine(job=job, to_cutter=to_cutter, sheet_width=sheet_width, sheet_height=sheet_height, output_filename=output) as virtual_machine:
        if power_steps is None:
            power_start = power_min
            lines_for_objects = virtual_machine.lines - 1  # minus one for axis
            power_steps = int(lines_for_objects / (max_passes - min_passes + 1))
            power_step_size = (power_max - power_min) / (power_steps - 1)  # minus 1 to include upper bound
        if speed_steps is None:
            speed_start = speed_min
            speed_steps = int(virtual_machine.columns - 1)  # minus one for axis
            speed_step_size = (speed_max - speed_min) / (speed_steps - 1)  # minus one to include upper bound

        assert job.sheet_width >= (virtual_machine.width) * ((power_steps) * (max_passes - min_passes + 1) + 1), \
                f'required width: {(virtual_machine.width) * ((power_steps) * (max_passes - min_passes + 1) + 1)}'
        assert job.sheet_height >= (virtual_machine.height) * (speed_steps + 1), \
                f'required height: {(virtual_machine.height) * (speed_steps + 1)}'

        virtual_machine.mark_fence_posts(speed_steps, power_steps * (max_passes - min_passes + 1))
        virtual_machine.save('fence')
        if fence_only:
            return

        # Speed axis numbers
        for row, speed in enumerate([speed_start + step * speed_step_size for step in range(speed_steps)]):
            virtual_machine.write_at(row, 0, int(round(speed, -1)))

        # Power / passes axis numbers
        column = 0
        for pa in range(min_passes, max_passes + 1):
            for step in range(power_steps):
                power = int(round(power_start + step * power_step_size, -1))
                virtual_machine.write_at(0, column, power, prepend=pa)
                column += 1

        virtual_machine.print_axes_writing()

        # Draw objects
        virtual_machine.set_machine_origin_to_graph_origin()
        column = 0
        for num_passes in range(min_passes, max_passes + 1):
            for _ in range(power_steps):
                power = int(round(power_start + column * power_step_size, -1))
                for row in range(speed_steps):
                    speed = int(round(speed_start + row * speed_step_size, -1))
                    virtual_machine.draw_at(row, column, power, speed, num_passes)
                column += 1

        if not laser:
            virtual_machine.remove_power_on_gcode()
            print("===============================================")
            print("Laser not switched on generated only movement !")
            print("===============================================")

if __name__ =="__main__":
    plac.call(generate)
