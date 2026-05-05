import yaml
from types import SimpleNamespace
import plac


def axes(power_start, power_stepsize, power_steps, speed_start, speed_stepsize, speed_steps, min_passes, max_passes):
    axes = ''
    for pa in range(max_passes - min_passes + 1):
        row = 0
        for ps in range(power_steps):
            s = f'{pa + 1} - {power_start + power_stepsize * ps:3} ({row})'
            axes = s + '\n' + axes
            row += 1
        axes = '-' * 8 * speed_steps + '\n' + axes
    axes = '\n\npass - power (n) \n' + axes
    axes += '         ' + '  '.join([f'{sp:5} ' for sp in range(speed_steps)]) + '\n'
    axes += '         ' + '  '.join([f'{speed_start + speed_stepsize * sp:6}' for sp in range(speed_steps)])
    return axes


class VirtualMachine:
    def __init__(self, job, filename='output', set_origin=True):
        self.snippets = SimpleNamespace(**yaml.safe_load(open('snippets.yaml')))
        self.digits = yaml.safe_load(open('digits.yaml'))
        self.filename = filename
        self.x = 0
        self.y = 0
        self.width = max(job.object_width, 7)
        self.hight = max(job.object_height, 4)
        self.sheet_width = job.sheet_width
        self.axes_power = job.axes_power
        self.axes_speed = job.axes_speed
        self.finished = False
        self.undo_x = 0
        self.undo_y = 0
        self.object = job.object
        self.gcode = ''
        self.gcode += self.snippets.start

    def __enter__(self):
        return self

    def __exit__(self, *arg):
        self.gcode += self.snippets.end
        with open(f'{self.filename}.gcode','w') as outputfile:
            outputfile.write(self.gcode)

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
            mm=self.hight
        assert mm >= 0
        self.y += mm
        self.gcode += self.snippets.move_origin_y.format(mm=-mm)

    def move_origin_down(self, mm=None):
        if mm is None:
            mm=self.hight
        assert mm >= 0
        self.y -= mm
        self.gcode += self.snippets.move_origin_y.format(mm=mm)

    def position(self, column=None, row=None):
        if column is not None:
            x = self.width * column
        else:
            x = self.undo_x
        if row is not None:
            y = self.hight * row
        else:
            y = self.undo_y

        self.gcode += self.snippets.undo_set_origin.format(x=self.undo_x, y=self.undo_y) + '\n'
        self.undo_x = x
        self.undo_y = y
        self.gcode += self.snippets.set_origin.format(x=x, y=y) + '\n'

    def draw_object(self, power, speed, num_passes):
        self.gcode += '\n'.join([self.object.format(power=power, speed=speed) for _ in range(num_passes)]) + '\nM5\n'

    def draw_at(self, column, row, power, speed, num_passes):
        self.position(column, row)
        self.draw_object(power, speed, num_passes)

    def write(self, number):
        assert number <= 99
        if number >= 10:
            self.gcode += self.digits[f'n{number // 10}0'].format(power=self.axes_power, speed=self.axes_speed)
        self.gcode += self.digits[f'n{number % 10}'].format(power=self.axes_power, speed=self.axes_speed)

    def write_at(self, column, row, first_number=None, second_number=None):
        self.position(column, row)
        self.write(first_number)
        if second_number is not None:
            self.position(column, row + 0.5)
            self.write(second_number)

    def hard_set_origin(self, x=None, y=None):
        """ Sets the current origin to (x, y), if x or y is None current
            position is set as origin """
        self.position(x, y)
        self.undo_x = 0
        self.undo_y = 0

    def new_square(self, power=20, speed=1500):
        end = self.sheet_width // self.width
        self.position(0, self.undo_y / self.hight + 1)
        for i in range(end):
            self.gcode += self.snippets.line_mm_right.format(power=power, speed=speed, mm=self.width / 2) + '\n'
            self.move_origin_right(self.width)
        self.hard_set_origin(x=0)

@plac.pos('power_start', type=int, help="Smallest power setting (percent, integer)")
@plac.pos('power_stepsize', type=int, help="Power increments")
@plac.pos('power_steps', type=int, help="Number of power steps")
@plac.pos('speed_start', type=int, help="Smallest speed setting")
@plac.pos('speed_stepsize', type=int, help="Speed increments")
@plac.pos('speed_steps', type=int, help="Number of speed steps")
@plac.pos('min_passes', type=int, help="Smallest number of passes")
@plac.pos('max_passes',type=int, help="Highest number of passes")
@plac.opt('job', type=str, help="job.yaml contains objects and size, defaults to job for job.yaml, see example.yaml")
def generate(power_start:int, power_stepsize:int, power_steps:int, speed_start:int, speed_stepsize:int, speed_steps:int, min_passes:int, max_passes:int, job='job'):
    """ A script that generates a gcode matrix with different power, speed, and pass number combinations to find optimal laser cutter setting.


        This generates gcode to print the gcode object in 'job.yaml' 200 times at different power, speed, and number of passes settings::

            python generate_test_gcode.py 5 5 7 500 250 10 1 4

            python generate_test_gcode.py  power_start  power_stepsize  power_steps  speed_start  speed_stepsize  speed_steps  min_passes  max_passes

        'job.yaml' contains the object's gcode and sizes of the object and the sheet as well as the power and
        speed with which the axis is engraved. Generate the gcode for the object you want to test in your favorite
        gcode generator (lightburn, rayforge ...). Make sure it is close to the origin. Note the width
        and height. Copy the object to 'job.yaml' and edit M5 and G1, to G5 commands as follows:

        The object's M4 commands must be changed to 'M4 S{POWER}'. The F value of all speed commands (G1 - G5) must be changed:
        from F1234 to F{speed}. For example, 'G1 X1.174 Y2.176 F1500' becomes 'G1 X1.174 Y2.176 F{speed}'.

        See 'example.yaml' for reference.

        The resulting gcode prints, but DOES NOT DISPLAY CORRECTLY IN GCODE VIEWERS.

    """
    print(axes(power_start, power_stepsize, power_steps, speed_start, speed_stepsize, speed_steps, min_passes, max_passes))

    job = SimpleNamespace(**yaml.safe_load(open(f'{job}.yaml')))
    assert job.sheet_width > job.object_width * speed_steps, \
            f'required width: {job.object_width * speed_steps}'
    assert job.sheet_height > job.object_height * power_steps * (max_passes - min_passes + 1), \
            f'required height: {job.object_height * power_steps * (max_passes - min_passes + 1)}'

    with VirtualMachine(job=job) as virtural_machine:
        for column in range(speed_steps):
            virtural_machine.write_at(column + 1, 0, column)

        row = 0
        for pa in range(max_passes - min_passes + 1):
            for power_step in range(power_steps):
                virtural_machine.write_at(0, row + 1, pa, power_step)
                row += 1

        virtural_machine.hard_set_origin(1, 1)
        for num_passes in range(min_passes, max_passes + 1):
            for row in range(power_steps):
                power = power_start + row * power_stepsize
                for column in range(speed_steps):
                    speed = speed_start + column * speed_stepsize
                    virtural_machine.draw_at(column, row, power, speed, num_passes)
            virtural_machine.new_square()

if __name__ =="__main__":
    plac.call(generate)
