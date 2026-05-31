from pprint import pprint
import yaml
from types import SimpleNamespace
import plac
from send_to_cutter import LaserStreamer
from helper import rename_digit_dict
from tqdm import tqdm as progress


class VirtualMachine:
    def __init__(self, job, laser, to_cutter, verbose, passes_on_y, sheet_width, sheet_height, machine, output_filename):
        with open('snippets.yaml') as snippets_file:
            self.snippets = SimpleNamespace(**yaml.safe_load(snippets_file))
        with open('digits.yaml') as digits_file:
            self.digits = rename_digit_dict(yaml.safe_load(digits_file))
        self.output_filename = output_filename
        self.machine = machine
        self.axis_width = (5 * (self.digits['letter_width']
                           + self.digits['distance_between_letters'])
                           + self.digits['axis_distance'])
        self.axis_height = 2 * self.digits['letter_height'] + self.digits['axis_distance']
        self.width = max(job.object_width, 2 * (self.digits['letter_width'] + self.digits['distance_between_letters']) + self.digits['distance_between_numbers'])
        self.height = max(job.object_height, self.digits['letter_height'])
        self.columns = int((sheet_width - self.axis_width) / self.width)
        self.rows = int((sheet_height - self.axis_height) / self.height)
        self.axes_writing = [['' for _ in range(self.columns + 1)] for __ in range(self.rows + 1)]
        self.axes_power = job.axes_power
        self.axes_speed = job.axes_speed
        self.border_x = self.width * self.columns + self.axis_width
        self.border_y = self.height * self.rows + self.axis_height
        self.x = 0
        self.y = 0
        self.object = job.object
        self.gcode = ''
        self.gcode += self.snippets.start
        self.to_cutter = to_cutter
        self.hard_column_offset = 0
        self.hard_row_offset = 0
        self.laser = laser
        self.verbose = verbose
        self.passes_on_y = passes_on_y

    def __enter__(self):
        return self

    def __exit__(self, *arg):
        if not self.laser:
            self.remove_power_on_gcode()
        self.save()
        if self.to_cutter:
            with LaserStreamer(self.machine, verbose=self.verbose) as laser_cutter:
                laser_cutter.stream(self.gcode)

    def save(self, output_filename=None):
        self.gcode += self.snippets.end
        if not self.laser:
            self.remove_power_on_gcode()
        if output_filename is None:
            output_filename = self.output_filename
        with open(f'{output_filename}.gcode','w') as outputfile:
            outputfile.write(self.gcode)
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

    def mark_fence_posts(self):
        self.gcode += self.snippets.fence.format(x=self.border_x, y=self.border_y, speed=250) + '\n'

    def write_at(self, row, column, number, prepend=None, double_line=False):
        if row is None:
                number = number // 10
        self.gcode += 'G90\n'
        if double_line:
            nstring = f'{int(number)}'
            up_for_extra_line = 0
        else:
            up_for_extra_line = self.digits['letter_height']
            nstring = f'{prepend:>2}-{int(number):<2}'  # letter d go down and left

        if column is None:
            self.axes_writing[row + 1][0] = nstring
            self.gcode += f'G0 X0 Y{self.axis_height + row * self.height + up_for_extra_line} F10000\n'
        elif row is None:
            self.axes_writing[0][column + 1] = nstring
            self.gcode += f'G0 X{self.axis_width + column * self.width} Y{up_for_extra_line} F10000\n'
        else:
            raise Exception()
        self.gcode += 'G91\n'

        for digit in nstring:
            self.gcode += self.digits[f'{digit}'].format(power=self.axes_power, speed=self.axes_speed) + '\n'
            self.gcode += self.digits['space'].format(space=self.digits['distance_between_letters']) + '\n'
        self.gcode += 'G90\n'

    def remove_power_on_gcode(self):
        gcode = [line
                 for line in self.gcode.split('\n')
                 if not line.strip().upper().startswith(('M3', 'M4', 'M5'))]
        self.gcode = ('\n').join(gcode)

    def print_axes_writing(self):
        for line in reversed(self.axes_writing):
            for cell in line:
                try:
                    print(f'{cell:<6}', end='')
                except (TypeError, ValueError):
                    print('.', end='')
            print()

    def calculate_steps(self, power_min, power_max, speed_min, speed_max, passes_min, passes_max, job):
        if self.passes_on_y:
            if not passes_max - passes_min + 1 <= self.rows:
                raise ValueError("More passes than rows")
            power_steps = self.columns
            speed_steps = int(self.rows // (passes_max - passes_min + 1))
        else:
            if not passes_max - passes_min + 1 <= self.columns:
                raise ValueError("More passes than columns")
            power_steps = int(self.columns  // (passes_max - passes_min + 1))
            speed_steps = self.rows

        if power_steps < 2 and power_max != power_max:
            raise ValueError("More passes than columns, reduce passes or set power_max = power_min")

        if speed_steps < 2 and speed_max != speed_min:
            raise ValueError("More passes than rows, reduce passes or set speed_max = speed_min")

        if power_min != power_max:
            power_step_size = (power_max - power_min) / (power_steps - 1)  # minus 1 to include upper bound
        else:
            power_step_size = 0
        if speed_max != speed_min:
            speed_step_size = (speed_max - speed_min) / (speed_steps - 1)  # minus one to include upper bound
        else:
            speed_step_size = 0

        self.power_steps = power_steps
        self.speed_steps = speed_steps

        return power_steps, speed_steps, power_step_size, speed_step_size

    def draw_x_axis(self, power_min, power_step_size, passes_min, passes_max):
        for column in range(self.columns):
            power = power_min + (column % self.power_steps) * power_step_size
            power = int(round(power, -1))
            num_passes = passes_min + column // self.power_steps
            if num_passes > passes_max:
                break
            self.write_at(None, column, power, prepend=num_passes, double_line=(self.columns == self.power_steps))

    def draw_y_axis(self, speed_min, speed_step_size, passes_min, passes_max):
        for row in range(self.rows):
            speed = speed_min + (row % self.speed_steps) * speed_step_size
            num_passes = passes_min + row // self.speed_steps
            if num_passes > passes_max:
                break
            self.write_at(row, None, round(speed, -1), prepend=num_passes, double_line=(self.rows == self.speed_steps))

    def draw_object_matrix(self, speed_min, speed_step_size, power_min, power_step_size, passes_min, passes_max):
        for row in range(self.rows):
            for column in range(self.columns):
                speed = speed_min + (row % self.speed_steps) * speed_step_size
                power = power_min + (column % self.power_steps) * power_step_size
                r = row // self.speed_steps
                c = column // self.power_steps
                num_passes = passes_min + max(r, c)
                if num_passes > passes_max:
                    break
                self.draw_at(row, column, power, speed, num_passes)
        return power


def generate(power_min, power_max, speed_min, speed_max, passes_min, passes_max,
             sheet_width=1, sheet_height=1,
             passes_on_y=False,
             job='job.yaml', machine='machine.yaml', output='output',
             laser=False, to_cutter=False, fence_only=False, verbose=False):

    power_max = int(power_max * 10)
    power_min = int(power_min * 10)
    with open(job) as job_file:
        job = SimpleNamespace(**yaml.safe_load(job_file))
    if sheet_width <= 1:
        sheet_width = job.sheet_width * sheet_width
    if sheet_height <= 1:
        sheet_height = job.sheet_height * sheet_height

    with VirtualMachine(job=job, laser=laser, machine=machine, to_cutter=to_cutter,
                        sheet_width=sheet_width, sheet_height=sheet_height, passes_on_y=passes_on_y,
                        output_filename=output, verbose=verbose) as virtual_machine:

        try:
            power_steps, speed_steps, power_step_size, speed_step_size = virtual_machine.calculate_steps(
                power_min, power_max, speed_min, speed_max, passes_min, passes_max, job)
        except ValueError as error:
            print(f'Error: {error}')
            return

        virtual_machine.mark_fence_posts()
        virtual_machine.save('fence')
        if fence_only:
            return

        virtual_machine.draw_x_axis(power_min, power_step_size, passes_min, passes_max)
        virtual_machine.draw_y_axis(speed_min, speed_step_size, passes_min, passes_max)

        virtual_machine.print_axes_writing()

        # Draw objects
        virtual_machine.set_machine_origin_to_graph_origin()
        power = virtual_machine.draw_object_matrix(speed_min, speed_step_size, power_min, power_step_size, passes_min, passes_max)

        if not laser:
            print("===============================================")
            print("Laser not switched on generated only movement !")
            print("===============================================")


@plac.pos('power_min', type=float, help="Smallest power setting (percent, accepts one digit after decimal point)")
@plac.pos('power_max', type=float, help="Highest power setting (percent, accepts one digit after decimal point)")
@plac.pos('speed_min', type=int, help="Smallest speed setting")
@plac.pos('speed_max', type=int, help="Highest speed setting")
@plac.pos('passes_min', type=int, help="Smallest number of passes")
@plac.pos('passes_max',type=int, help="Highest number of passes")
@plac.opt('job', type=str, help="job-yaml contains objects and size. Default: 'job.yaml'")
@plac.opt('machine', type=str, help="machine-yaml contains machine address, timeouts, and parameters. Default: 'machine.yaml'")
@plac.opt('output', type=str, help="output filename, defaults to 'output.gcode'")
@plac.flg('laser', help="Switch laser on")
@plac.flg('to_cutter', abbrev='c', help="Operates the lasercutter specfied in machine.yaml directly")
@plac.opt('sheet_width', abbrev='sw', type=float, help="Optional: Fraction of sheet width defined in job yaml")
@plac.opt('sheet_height', abbrev='sh', type=float, help="Optional: Fraction of sheet hight defined in job yaml")
@plac.flg('fence_only', help="Only mark the fence")
@plac.flg('verbose', help="Verbose")
@plac.flg('passes_on_y', help="Passes on y axis")
def main(power_min, power_max, speed_min, speed_max, passes_min, passes_max,
             sheet_width=1, sheet_height=1,
             passes_on_y=False,
             job='job.yaml', machine='machine.yaml', output='output',
             laser=False, to_cutter=False, fence_only=False, verbose=False):
    """ A script that generates a gcode matrix with different power, speed, and pass number combinations to find optimal laser cutter setting.


    This generates gcode to print the gcode object in 'job.yaml' 200 times at different power, speed, and number of passes settings::

        python start_gcode_test.py 50 400 100 10000 1 4 --laser --to-cutter

        python start_gcode_test.py power_min power_max speed_min speed_max passes_min passes_max [--laser switches on] [--to_cutter sends directly to cutter]

    See README.md how to change the object that is cut out at different speed, power, and pass numbers.
    Edit machine.yaml to use 'to_cutter' command.

    The object's M4 commands must be changed to 'M4 S{POWER}'. The F value of all speed commands (G1 - G5) must be changed:
    from F1234 to F{speed}. For example, 'G1 X1.174 Y2.176 F1500' becomes 'G1 X1.174 Y2.176 F{speed}'.

    generated gcode in fence.gcode (which only moves around the cutting aread) and output.gcode which lasers.

    The resulting gcode prints, but DOES NOT DISPLAY CORRECTLY IN GCODE VIEWERS.
    The gcode viewer at https://nraynaud.github.io/webgcode/ works.

    """

    generate(power_min, power_max, speed_min, speed_max, passes_min, passes_max,
             sheet_width, sheet_height,
             passes_on_y, job, machine, output,
             laser, to_cutter, fence_only, verbose)


if __name__ =="__main__":
    plac.call(main)
