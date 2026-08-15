def calculate_volume_score(
    volume_ratio: float,
    signal: str,
):
    score = 0

    if volume_ratio >= 3.0:
        score = 25

    elif volume_ratio >= 2.0:
        score = 20

    elif volume_ratio >= 1.3:
        score = 10

    return score