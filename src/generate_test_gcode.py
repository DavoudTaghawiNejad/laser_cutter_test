import yaml
from types import SimpleNamespace
import plac
from send_to_cutter import LaserStreamer
from helper import rename_digit_dict


MIN_DIGITS = 4
SPACE = 0.5

def generate_axes_ascii(power_start, power_stepsize, power_steps, speed_start, speed_stepsize, speed_steps, min_passes, max_passes):
    axes = ''
    for pa in range(min_passes, max_passes + 1):
        row = 0
        for ps in range(power_steps):
            s = f'{pa} - {power_start + power_stepsize * ps:3} ({row})'
            axes = s + '\n' + axes
            row += 1
        axes = '-' * 8 * speed_steps + '\n' + axes
    axes = '\n\npass - power (n) \n' + axes
    axes += '         ' + '  '.join([f'{sp:5} ' for sp in range(speed_steps)]) + '\n'
    axes += '         ' + '  '.join([f'{speed_start + speed_stepsize * sp:6}' for sp in range(speed_steps)])
    return axes


class VirtualMachine:
    def __init__(self, job, to_cutter, output_filename='output'):
        with open('snippets.yaml') as snippets_file:
            self.snippets = SimpleNamespace(**yaml.safe_load(snippets_file))
        with open('digits.yaml') as digits_file:
            self.digits = rename_digit_dict(yaml.safe_load(digits_file))
        self.output_filename = output_filename
        self.num_digits = max(MIN_DIGITS, job.object_width // self.digits['letter_width'])
        self.width = max(job.object_width, self.num_digits * (self.digits['letter_width']) + SPACE)
        self.height = max(job.object_height, self.digits['letter_height'])
        self.sheet_width = job.sheet_width
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

    def move_origin_right(self, mm=None):
        if mm is None:
            mm=self.width
        assert mm >= 0
        self.x += mm
        self.gcode += self.snippets.move_origin_x.format(mm=-mm)

    def move_origin_left(self, mm=None):
        if mm is None:
            mm=self.width
        assert mm >= 0
        self.x -= mm
        self.gcode += self.snippets.move_origin_x.format(mm=mm)


    def move_origin_up(self, mm=None):
        if mm is None:
            mm=self.height
        assert mm >= 0
        self.y += mm
        self.gcode += self.snippets.move_origin_y.format(mm=-mm)

    def move_origin_down(self, mm=None):
        if mm is None:
            mm=self.height
        assert mm >= 0
        self.y -= mm
        self.gcode += self.snippets.move_origin_y.format(mm=mm)

    def position(self, column=None, row=None):
        if column is not None:
            x = self.width * (column + self.hard_column_offset)
        else:
            x = self.x
        if row is not None:
            y = self.height * (row + self.hard_row_offset)
        else:
            y = self.y
        self.x = x
        self.y = y
        self.gcode += self.snippets.set_origin.format(x=x, y=y) + '\n'
        self.gcode +='G0 X0 Y0\n'


    def hard_set_origin(self, column=None, row=None):
        if column is not None:
            self.hard_column_offset = column

        if row is not None:
            self.hard_row_offset = row

    def draw_object(self, power, speed, num_passes):
        self.gcode += '\n'.join([self.object.format(power=power, speed=speed) for _ in range(num_passes)]) + '\nM5\n'

    def draw_at(self, column, row, power, speed, num_passes):
        self.position(column, row)
        self.draw_object(power, speed, num_passes)

    def mark_fence_post(self, column, row):
        self.position(column, row)
        self.gcode += self.snippets.fence_mark.format(width=self.width, height=self.height)

    def write_at(self, column, row, number):
        if len(str(number)) < self.num_digits:
            nstring = str(number)
        else:
            nstring = str(number / 1000).lstrip("0")[:self.num_digits]
        self.position(0, 0)
        self.gcode += 'G91\n'
        self.gcode += f'G0 X{column * self.width} Y{row * self.height}\n'
        for digit in nstring:
            self.gcode += self.digits['space'].format(space=self.digits['letter_space']) + '\n'
            self.gcode += self.digits[f'{digit}'].format(power=self.axes_power, speed=self.axes_speed) + '\n'
        self.gcode += 'G90\n'

    def remove_power_on_gcode(self):
        gcode = [line
                 for line in self.gcode.split('\n')
                     if not line[0:2] in ['M3', 'M4', 'M5', 'M10', 'M11', 'M42', 'M106']]
        self.gcode = ('\n').join(gcode)




@plac.pos('power_start', type=int, help="Smallest power setting (percent, integer)")
@plac.pos('power_stepsize', type=int, help="Power increments")
@plac.pos('power_steps', type=int, help="Number of power steps")
@plac.pos('speed_start', type=int, help="Smallest speed setting")
@plac.pos('speed_stepsize', type=int, help="Speed increments")
@plac.pos('speed_steps', type=int, help="Number of speed steps")
@plac.pos('min_passes', type=int, help="Smallest number of passes")
@plac.pos('max_passes',type=int, help="Highest number of passes")
@plac.opt('job', type=str, help="job.yaml contains objects and size, defaults to job for job.yaml, see example.yaml")
@plac.opt('output', type=str, help="output filename, defaults to 'output.gcode'")
@plac.flg('laser', help="Switch laser on")
@plac.flg('to_cutter', help="Operates the lasercutter specfied in machine.yaml directly")
def generate(power_start:int, power_stepsize:int, power_steps:int, speed_start:int, speed_stepsize:int, speed_steps:int, min_passes:int, max_passes:int,
             job='job', output='output', laser=False, to_cutter=False):
    """ A script that generates a gcode matrix with different power, speed, and pass number combinations to find optimal laser cutter setting.


        This generates gcode to print the gcode object in 'job.yaml' 200 times at different power, speed, and number of passes settings::

            python generate_test_gcode.py 5 5 7 500 250 10 1 4 --laser --to-cutter

            python generate_test_gcode.py  power_start  power_stepsize  power_steps  speed_start  speed_stepsize  speed_steps  min_passes  max_passes [--laser switches on] [--to_cutter sends directly to cutter]

        See README.md how to change the object that is cut out at different speed, power, and pass numbers.
        Edit machine.yaml to use 'to_cutter' command.

        The object's M4 commands must be changed to 'M4 S{POWER}'. The F value of all speed commands (G1 - G5) must be changed:
        from F1234 to F{speed}. For example, 'G1 X1.174 Y2.176 F1500' becomes 'G1 X1.174 Y2.176 F{speed}'.

        generated gcode in fence.gcode (which only moves around the cutting aread) and output.gcode which lasers.

        The resulting gcode prints, but DOES NOT DISPLAY CORRECTLY IN GCODE VIEWERS.

    """
    print(generate_axes_ascii(power_start, power_stepsize, power_steps, speed_start, speed_stepsize, speed_steps, min_passes, max_passes))
    with open('job.yaml') as job_file:
        job = SimpleNamespace(**yaml.safe_load(job_file))
    assert job.sheet_width >= (max(job.object_width, 7) + 1) * speed_steps, \
            f'required width: {(max(job.object_width, 7) + 1) * speed_steps}'
    assert job.sheet_height >= (max(job.object_height, 4) + 1) * power_steps * (max_passes - min_passes + 1), \
            f'required height: {(max(job.object_height, 4) + 1) * power_steps * (max_passes - min_passes + 1)}'

    with VirtualMachine(job=job, to_cutter=to_cutter, output_filename=output) as virtual_machine:
        # outer perimeter
        virtual_machine.mark_fence_post(0, 0)
        virtual_machine.mark_fence_post(speed_steps + 1, 0)
        virtual_machine.mark_fence_post(speed_steps + 1, power_stepsize * (max_passes - min_passes + 1) + 1,)
        virtual_machine.mark_fence_post(0, power_stepsize * (max_passes - min_passes + 1) + 1)
        virtual_machine.save('fence')
        virtual_machine.position(0, 0)

        # Speed axis numbers
        for column, speed in enumerate([speed_start + step * speed_stepsize for step in range(speed_steps)]):
            virtual_machine.write_at(column + 1, 0, speed)

        # Power / passes axis numbers
        row = 0
        for pa in range(min_passes, max_passes + 1):
            for power in [power_start + step * power_stepsize for step in range(power_steps)]:
                virtual_machine.position(0, row + 1)
                virtual_machine.write_at(0, row + 1, power)
                row += 1

        virtual_machine.hard_set_origin(1, 1)
        row = 0
        for num_passes in range(min_passes, max_passes + 1):
            for _ in range(power_steps):
                power = power_start + row * power_stepsize
                for column in range(speed_steps):
                    speed = speed_start + column * speed_stepsize
                    virtual_machine.draw_at(column, row, power, speed, num_passes)
                row += 1


        if not laser:
            virtual_machine.remove_power_on_gcode()
            print("===============================================")
            print("Laser not switched on generated only movement !")
            print("===============================================")

if __name__ =="__main__":
    plac.call(generate)
