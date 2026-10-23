"""Customer population wording from held field facts."""


def population_value(population, percent=None):
    percent = population.get("percent") if population.get("percent") is not None else percent
    sampled = population.get("populatedRecordsCount")
    used = population.get("usedInRecordsCount")
    if sampled is not None and used is not None:
        if percent is None:
            percent = round(100 * used / sampled, 2) if sampled else 0
        return f"{used:,} of {sampled:,} sampled records hold a value ({percent}%)"
    return percent if percent is not None and percent != "" else "not known"


def population_text(population, percent=None):
    value = population_value(population, percent)
    return f"{value}%" if not isinstance(value, str) or value.replace(".", "", 1).isdigit() else value
