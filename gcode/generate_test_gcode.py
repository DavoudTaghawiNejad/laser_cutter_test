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
class Square:
    def __init__(self, snippet_file, job, set_origin=True):
        self.snippets = snippet_file
        self.x = 0
        self.y = 0
        self.width = job.object_width
        self.hight = job.object_height
        self.finished = False
        self.undo_x = 0
        self.undo_y = 0
        self.object = job.object

    def __enter__(self):
        return self

    def __exit__(self, *arg):
        pass

    def right(self, mm=None):
        if mm is None:
            mm=self.width
        assert mm >= 0
        self.x += mm
        return self.snippets.move_origin_x.format(mm=-mm)

    def left(self, mm=None):
        if mm is None:
            mm=self.width
        assert mm >= 0
        self.x -= mm
        return self.snippets.move_origin_x.format(mm=mm)


    def up(self, mm=None):
        if mm is None:
            mm=self.hight
        assert mm >= 0
        self.y += mm
        return self.snippets.move_origin_y.format(mm=-mm)

    def down(self, mm=None):
        if mm is None:
            mm=self.hight
        assert mm >= 0
        self.y -= mm
        return self.snippets.move_origin_y.format(mm=mm)

    def position(self, column, row):
        undo = self.snippets.undo_set_origin.format(x=self.undo_x, y=self.undo_y)
        self.undo_x = self.width * column
        self.undo_y = self.hight * row
        return undo + '\n' + self.snippets.set_origin.format(x=self.width * column, y=self.hight * row)


    def draw_object(self, power, speed, num_passes):
        return '\n'.join([self.object.format(power=power, speed=speed) for _ in range(num_passes)])


    def draw_at(self, column, row, power, speed, num_passes):
        return self.position(column, row) + '\n' + self.draw_object(power, speed, num_passes)

    def hard_set_origin(self, x=None, y=None):
        """ Sets the current origin to (x, y), if x or y is None current
            position is set as origin """
        if x is None:
            x = self.undo_y
        if y is None:
            y = self.undo_y
        self.undo_x = 0
        self.undo_y = 0
        return self.snippets.set_origin.format(x=x, y=y)

    def new_square(self, power=20, speed=1500):
        end = self.x // self.width
        left = self.position(0, self.undo_y / self.hight + 1)
        line = '\n'.join([self.snippets.line_mm_right.format(power=power, speed=speed, mm=self.width / 2) + '\n' + self.right()
                          for i in range(end)])
        return left + line + self.hard_set_origin()

@plac.pos('power_start', type=int, help="Smalles power setting (percent, integer)")
@plac.pos('power_stepsize', type=int, help="Power increments")
@plac.pos('power_steps', type=int, help="Number of power steps")
@plac.pos('speed_start', type=int, help="Smallest speed setting")
@plac.pos('speed_stepsize', type=int, help="Speed increments")
@plac.pos('speed_steps', type=int, help="Number of speed steps")
@plac.pos('min_passes', type=int, help="Smallest Number of passes")
@plac.pos('max_passes' ,type=int, help="Highest Number of passes")
def generate(power_start:int, power_stepsize:int, power_steps:int, speed_start:int, speed_stepsize:int, speed_steps:int, min_passes:int, max_passes:int):
    print(axes(power_start, power_stepsize, power_steps, speed_start, speed_stepsize, speed_steps, min_passes, max_passes))
    snippets = SimpleNamespace(**yaml.safe_load(open('snippets.yaml')))
    job = SimpleNamespace(**yaml.safe_load(open('job.yaml')))
    assert job.sheet_width > job.object_width * speed_steps, \
            f'required width: {job.object_width * speed_steps}'
    assert job.sheet_height > job.object_height * power_steps * (max_passes - min_passes + 1), \
            f'required height: {job.object_height * power_steps * (max_passes - min_passes + 1)}'

    gcode = [snippets.start]
    with Square(snippet_file=snippets, job=job) as square:
        for num_passes in range(min_passes, max_passes + 1):
            for row in range(power_steps):
                power = power_start + row * power_stepsize
                for column in range(speed_steps):
                    speed = speed_start + column * speed_stepsize
                    gcode.append(square.draw_at(column, row, power, speed, num_passes))
            gcode.append(square.new_square())
    gcode.append(snippets.end)

    open('output.gcode','w').write('\n'.join(gcode))


if __name__ =="__main__":
    plac.call(generate)
