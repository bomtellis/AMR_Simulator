from datetime import datetime, timedelta


class SimulationClock:
    def __init__(self, start_datetime: datetime, tick_rate: float = 60.0):
        self.start_datetime = start_datetime
        self.tick_rate = tick_rate

    def sim_seconds_to_datetime(self, seconds: float) -> datetime:
        return self.start_datetime + timedelta(seconds=seconds)

    def format_sim_time(self, seconds: float) -> str:
        return self.sim_seconds_to_datetime(seconds).isoformat(
            sep=" ", timespec="seconds"
        )


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours:02}:{minutes:02}:{secs:02}"
    return f"{hours:02}:{minutes:02}:{secs:02}"


def parse_release_time(task_dict: dict, start_datetime: datetime) -> float:
    if "release_datetime" in task_dict:
        dt = parse_datetime(task_dict["release_datetime"])
        return max(0.0, (dt - start_datetime).total_seconds())
    return float(task_dict.get("release_time", 0.0))
