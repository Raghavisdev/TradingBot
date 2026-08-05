def trend(values):

    if len(values) < 5:
        return 0

    recent = sum(values[-5:]) / 5

    older = sum(values[:5]) / 5

    return recent - older