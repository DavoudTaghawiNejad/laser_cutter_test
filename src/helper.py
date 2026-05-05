def rename_digit_dict(data):
    data = dict(data)
    transformed = {}
    for key, value in data.items():
        if key[0] == 'n':
            transformed[key[1]] = value
        elif key == 'spacebar':
            transformed[' '] = value
        elif key == 'decimaldot':
            transformed['.'] = value
        elif key == 'dash':
            transformed['-'] = value
        else:
            transformed[key] = value

    return transformed
