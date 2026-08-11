def calculate_volume_score(volume_ratio: float):
    if volume_ratio >= 3.0:
        return 25

    elif volume_ratio >= 2.0:
        return 20

    elif volume_ratio >= 1.3:
        return 10

    return 0