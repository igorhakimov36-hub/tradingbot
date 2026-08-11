def calculate_funding_score(funding_rate: float):
    funding_abs = abs(funding_rate)

    if funding_abs >= 0.0010:
        return 15

    elif funding_abs >= 0.0005:
        return 10

    elif funding_abs >= 0.0001:
        return 5

    return 0