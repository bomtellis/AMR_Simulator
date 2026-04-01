import json
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
START_DATE = datetime(2026, 1, 5)  # Monday
NUM_DAYS = 7
SHIFT_OUT_OF_HOURS_TASKS = True

# Limit operating hours by task type rather than payload.
# Hours are inclusive start, exclusive end: [start_hour, end_hour)
TASK_TYPE_HOUR_LIMITS = {
    "food_delivery": (6, 20),
    "empty_trolley_return": (7, 22),
    "crockery_return": (11, 22),
    "drug_delivery": None,          # 24/7
    "specimen_run": None,           # 24/7
    "linen_delivery": (6, 18),
    "goods_delivery": (6, 20),
    "waste_collection": None,       # 24/7
    "kitchen_support": (5, 21),
}

# Optional fallback if you prefer to constrain by payload as well.
# Leave as None to disable payload-based checks.
PAYLOAD_HOUR_LIMITS = {
    "food_trolley": None,
    "drugs_box": None,
    "linen_cart": None,
    "goods_cage": None,
}

# ------------------------------------------------------------------
# LOCATIONS
# ------------------------------------------------------------------
LOCATIONS = [
    {"name": "OPD2-DH", "floor": 0},
    {"name": "OPD1-DH", "floor": 0},
    {"name": "UEC-DH", "floor": 0},
    {"name": "SDEC-DH", "floor": 0},
    {"name": "FRAILTY-DELIVERYHUB", "floor": 0},
    {"name": "RD", "floor": 0},
    {"name": "RD2", "floor": 0},
    {"name": "FRAILTY-DH", "floor": 0},
    {"name": "PHARMACY-DH", "floor": 0},
    {"name": "AMU-DELIVERYHUB", "floor": 0},
    {"name": "AMU-DH", "floor": 0},
    {"name": "MORTUARY-DH", "floor": 0},
    {"name": "THEATRES3-DH", "floor": 1},
    {"name": "THEATRES-STORE2", "floor": 1},
    {"name": "THEATRES-STORE", "floor": 1},
    {"name": "THEATRES1-DH", "floor": 1},
    {"name": "THEATRES2-DH", "floor": 1},
    {"name": "ICU-DH", "floor": 1},
    {"name": "ENDOSCOPY-DH", "floor": 1},
    {"name": "OPD4-DH", "floor": 1},
    {"name": "OPD3-DH", "floor": 1},
    {"name": "BIRTHING-SUITE-DH", "floor": 1},
    {"name": "NEONATAL-DH", "floor": 1},
    {"name": "ANTE-DH", "floor": 1},
    {"name": "KITCHEN", "floor": 2},
    {"name": "KITCHEN-DH", "floor": 2},
    {"name": "AMR-CENTRE", "floor": 2},
    {"name": "ADULTIP1-DH", "floor": 3},
    {"name": "MATERNITY-DH", "floor": 3},
    {"name": "MATERNITY-DELIVERYHUB", "floor": 3},
    {"name": "ADULTIP2-DH", "floor": 3},
    {"name": "ADULTIP2-DELIVERYHUB", "floor": 3},
    {"name": "ADULTIP5-DH", "floor": 4},
    {"name": "ADULTIP3-DH", "floor": 4},
    {"name": "ADULTIP3-DELIVERYHUB", "floor": 4},
    {"name": "ADULTIP4-DH", "floor": 4},
    {"name": "ADULTIP4-DELIVERYHUB", "floor": 4},
    {"name": "ADULTIP6-DELIVERYHUB", "floor": 5},
    {"name": "ADULTIP6-DH", "floor": 5},
    {"name": "ADULTIP7-DH", "floor": 5},
    {"name": "ADULTIP7-DELIVERYHUB", "floor": 5},
]

ALL_LOCATION_NAMES = [location["name"] for location in LOCATIONS]
DELIVERY_HUBS = [name for name in ALL_LOCATION_NAMES if "DELIVERYHUB" in name]
DISPOSAL_HOLDS = [name for name in ALL_LOCATION_NAMES if name.endswith("-DH")]

# Wards with meal delivery hubs. Excludes outpatients, theatres and ICU.
WARD_DELIVERY_HUBS = sorted(
    [
        name
        for name in DELIVERY_HUBS
        if not any(exclusion in name for exclusion in ["OPD", "THEATRES", "ICU"])
    ]
)

DELIVERYHUB_TO_DH = {
    "FRAILTY-DELIVERYHUB": "FRAILTY-DH",
    "AMU-DELIVERYHUB": "AMU-DH",
    "MATERNITY-DELIVERYHUB": "MATERNITY-DH",
    "ADULTIP2-DELIVERYHUB": "ADULTIP2-DH",
    "ADULTIP3-DELIVERYHUB": "ADULTIP3-DH",
    "ADULTIP4-DELIVERYHUB": "ADULTIP4-DH",
    "ADULTIP6-DELIVERYHUB": "ADULTIP6-DH",
    "ADULTIP7-DELIVERYHUB": "ADULTIP7-DH",
}

# ------------------------------------------------------------------
# TASK GENERATOR
# ------------------------------------------------------------------
class HospitalTaskGenerator:
    def __init__(self):
        self.tasks = []
        self.next_id = 1

        self.pharmacy_targets = sorted(
            set(
                WARD_DELIVERY_HUBS
                + [
                    "ICU-DH",
                    "NEONATAL-DH",
                    "BIRTHING-SUITE-DH",
                    "ANTE-DH",
                    "THEATRES1-DH",
                    "THEATRES2-DH",
                    "THEATRES3-DH",
                    "ENDOSCOPY-DH",
                    "UEC-DH",
                    "SDEC-DH",
                    "OPD1-DH",
                    "OPD2-DH",
                    "OPD3-DH",
                    "OPD4-DH",
                ]
            )
        )

        self.goods_targets = [
            "THEATRES-STORE",
            "THEATRES-STORE2",
            "ENDOSCOPY-DH",
            "UEC-DH",
            "SDEC-DH",
            "PHARMACY-DH",
            "KITCHEN-DH",
        ] + WARD_DELIVERY_HUBS

        self.linen_targets = [
            "ADULTIP1-DH",
            "ADULTIP2-DH",
            "ADULTIP3-DH",
            "ADULTIP4-DH",
            "ADULTIP5-DH",
            "ADULTIP6-DH",
            "ADULTIP7-DH",
            "MATERNITY-DH",
            "NEONATAL-DH",
            "ANTE-DH",
            "BIRTHING-SUITE-DH",
            "ICU-DH",
            "THEATRES1-DH",
            "THEATRES2-DH",
            "THEATRES3-DH",
            "ENDOSCOPY-DH",
            "AMU-DH",
            "FRAILTY-DH",
            "UEC-DH",
            "SDEC-DH",
        ]

        self.specimen_sources = WARD_DELIVERY_HUBS + [
            "ICU-DH",
            "NEONATAL-DH",
            "BIRTHING-SUITE-DH",
            "UEC-DH",
            "SDEC-DH",
            "AMU-DH",
            "FRAILTY-DH",
        ]

    # --------------------------------------------------------------
    # TIME RULES
    # --------------------------------------------------------------
    @staticmethod
    def _within_hour_window(dt: datetime, hour_window: tuple[int, int] | None) -> bool:
        if hour_window is None:
            return True
        start_hour, end_hour = hour_window
        return start_hour <= dt.hour < end_hour

    def is_task_allowed_at(self, payload: str, task_type: str, dt: datetime) -> bool:
        task_type_window = TASK_TYPE_HOUR_LIMITS.get(task_type)
        payload_window = PAYLOAD_HOUR_LIMITS.get(payload)
        return self._within_hour_window(dt, task_type_window) and self._within_hour_window(dt, payload_window)

    def move_into_allowed_window(self, payload: str, task_type: str, dt: datetime) -> datetime:
        """
        Move a task into the next available valid hour window.
        Task-type limits are applied first, then payload limits.
        """
        dt = self._move_into_single_window(dt, TASK_TYPE_HOUR_LIMITS.get(task_type))
        dt = self._move_into_single_window(dt, PAYLOAD_HOUR_LIMITS.get(payload))
        return dt

    @staticmethod
    def _move_into_single_window(dt: datetime, hour_window: tuple[int, int] | None) -> datetime:
        if hour_window is None:
            return dt

        start_hour, end_hour = hour_window
        if start_hour <= dt.hour < end_hour:
            return dt

        if dt.hour < start_hour:
            return dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)

        next_day = dt + timedelta(days=1)
        return next_day.replace(hour=start_hour, minute=0, second=0, microsecond=0)

    def add_task(
        self,
        pickup: str,
        dropoff: str,
        payload: str,
        dt: datetime,
        priority: int,
        task_type: str,
        shift_out_of_hours: bool = SHIFT_OUT_OF_HOURS_TASKS,
    ) -> None:
        if shift_out_of_hours:
            dt = self.move_into_allowed_window(payload, task_type, dt)

        if not self.is_task_allowed_at(payload, task_type, dt):
            return

        self.tasks.append(
            {
                "id": f"T{self.next_id:05d}",
                "pickup": pickup,
                "dropoff": dropoff,
                "payload": payload,
                "task_type": task_type,
                "release_datetime": dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "priority": int(priority),
            }
        )
        self.next_id += 1

    # --------------------------------------------------------------
    # GENERATION LOGIC
    # --------------------------------------------------------------
    def generate(self, start_date: datetime, num_days: int) -> list[dict]:
        for day_offset in range(num_days):
            day = start_date + timedelta(days=day_offset)
            is_weekend = day.weekday() >= 5

            self._generate_food_service(day)
            self._generate_pharmacy(day, is_weekend)
            self._generate_linen(day, is_weekend)
            self._generate_goods(day, is_weekend)
            self._generate_waste(day)
            # self._generate_specimens(day, is_weekend)
            # self._generate_kitchen_support(day)

        self.tasks.sort(key=lambda item: (item["release_datetime"], item["id"]))
        for index, task in enumerate(self.tasks, start=1):
            task["id"] = f"T{index:05d}"
        return self.tasks

    def _generate_food_service(self, day: datetime) -> None:
        meal_patterns = [
            (7, 35, 24, "breakfast"),
            (11, 10, 22, "lunch_1"),
            (12, 10, 22, "lunch_2"),
            (16, 10, 22, "evening_1"),
            (17, 10, 22, "evening_2"),
        ]

        for start_hour, start_minute, base_priority, meal_name in meal_patterns:
            wave_start = day.replace(hour=start_hour, minute=start_minute)

            for index, ward_hub in enumerate(WARD_DELIVERY_HUBS):
                dispatch_time = wave_start + timedelta(minutes=(2 * index) + random.randint(0, 2))
                pickup = "KITCHEN"

                priority = base_priority
                if "ADULTIP" in ward_hub:
                    priority += 4
                elif ward_hub in ["AMU-DELIVERYHUB", "FRAILTY-DELIVERYHUB"]:
                    priority += 2

                self.add_task(
                    pickup=pickup,
                    dropoff=ward_hub,
                    payload="food_trolley",
                    dt=dispatch_time,
                    priority=priority,
                    task_type="food_delivery",
                )

                return_time = dispatch_time + timedelta(minutes=random.randint(45, 90))
                self.add_task(
                    pickup=ward_hub,
                    dropoff="KITCHEN-DH",
                    payload="food_trolley",
                    dt=return_time,
                    priority=max(10, priority - 8),
                    task_type="empty_trolley_return",
                )

                if meal_name.startswith("breakfast") or meal_name.startswith("lunch") or meal_name.startswith("evening"):
                    crockery_time = dispatch_time + timedelta(minutes=random.randint(55, 110))
                    self.add_task(
                        pickup=ward_hub,
                        dropoff="KITCHEN-DH",
                        payload="food_trolley",
                        dt=crockery_time,
                        priority=max(11, priority - 7),
                        task_type="crockery_return",
                    )

    def _generate_pharmacy(self, day: datetime, is_weekend: bool) -> None:
        rounds = [(8, 15, 18), (14, 0, 17)] if not is_weekend else [(8, 30, 18), (15, 0, 16)]

        for round_hour, round_minute, base_priority in rounds:
            round_start = day.replace(hour=round_hour, minute=round_minute)
            for index, target in enumerate(self.pharmacy_targets):
                if is_weekend and target.startswith("OPD"):
                    continue

                dispatch_time = round_start + timedelta(minutes=(3 * index) + random.randint(0, 2))
                priority = base_priority

                if target in [
                    "ICU-DH",
                    "NEONATAL-DH",
                    "THEATRES1-DH",
                    "THEATRES2-DH",
                    "THEATRES3-DH",
                    "BIRTHING-SUITE-DH",
                ]:
                    priority += 6
                elif "DELIVERYHUB" in target:
                    priority += 2

                self.add_task(
                    pickup="PHARMACY-DH",
                    dropoff=target,
                    payload="drugs_box",
                    dt=dispatch_time,
                    priority=priority,
                    task_type="drug_delivery",
                )

        urgent_count = 8 if not is_weekend else 5
        urgent_targets = [target for target in self.pharmacy_targets if not (is_weekend and target.startswith("OPD"))]

        for _ in range(urgent_count):
            target = random.choice(urgent_targets)
            dispatch_time = day.replace(
                hour=random.choice([9, 10, 11, 13, 15, 16, 18, 20]),
                minute=random.randint(0, 59),
            )
            priority = 28 if target in [
                "ICU-DH",
                "NEONATAL-DH",
                "THEATRES1-DH",
                "THEATRES2-DH",
                "THEATRES3-DH",
                "BIRTHING-SUITE-DH",
            ] else 24

            self.add_task(
                pickup="PHARMACY-DH",
                dropoff=target,
                payload="drugs_box",
                dt=dispatch_time,
                priority=priority,
                task_type="drug_delivery",
            )

    def _generate_linen(self, day: datetime, is_weekend: bool) -> None:
        rounds = [(6, 45, 16), (13, 15, 14)] if not is_weekend else [(7, 15, 15)]
        targets = self.linen_targets if not is_weekend else [target for target in self.linen_targets if not target.startswith("OPD")]

        for round_hour, round_minute, base_priority in rounds:
            round_start = day.replace(hour=round_hour, minute=round_minute)
            for index, target in enumerate(targets):
                dispatch_time = round_start + timedelta(minutes=(4 * index) + random.randint(0, 2))
                pickup = "RD" if index % 2 == 0 else "RD2"
                priority = base_priority + (
                    3
                    if target in ["ICU-DH", "NEONATAL-DH", "THEATRES1-DH", "THEATRES2-DH", "THEATRES3-DH"]
                    else 0
                )

                self.add_task(
                    pickup=pickup,
                    dropoff=target,
                    payload="linen_cart",
                    dt=dispatch_time,
                    priority=priority,
                    task_type="linen_delivery",
                )

    def _generate_goods(self, day: datetime, is_weekend: bool) -> None:
        rounds = [(8, 0, 13), (15, 30, 12)] if not is_weekend else [(9, 0, 12)]
        targets = self.goods_targets if not is_weekend else [target for target in self.goods_targets if not target.startswith("OPD")]

        for round_hour, round_minute, base_priority in rounds:
            round_start = day.replace(hour=round_hour, minute=round_minute)
            for index, target in enumerate(targets):
                dispatch_time = round_start + timedelta(minutes=(5 * index) + random.randint(0, 3))
                pickup = "RD" if random.random() < 0.55 else "RD2"
                priority = base_priority + (3 if "THEATRES" in target or target == "ENDOSCOPY-DH" else 0)

                self.add_task(
                    pickup=pickup,
                    dropoff=target,
                    payload="goods_cage",
                    dt=dispatch_time,
                    priority=priority,
                    task_type="goods_delivery",
                )

    def _generate_waste(self, day: datetime) -> None:
        collection_windows = [(0, 0), (4, 0), (8, 0), (12, 0), (16, 0), (20, 0)]
        waste_holds = [hold for hold in DISPOSAL_HOLDS if hold not in ["KITCHEN-DH", "PHARMACY-DH"]]

        for window_hour, window_minute in collection_windows:
            window_start = day.replace(hour=window_hour, minute=window_minute)
            for index, hold in enumerate(waste_holds):
                dispatch_time = window_start + timedelta(minutes=((index * 5) % 240) + random.randint(0, 4))
                destination = "RD" if index % 2 == 0 else "RD2"
                priority = 19 if hold in [
                    "ICU-DH",
                    "THEATRES1-DH",
                    "THEATRES2-DH",
                    "THEATRES3-DH",
                    "NEONATAL-DH",
                    "BIRTHING-SUITE-DH",
                ] else 15

                self.add_task(
                    pickup=hold,
                    dropoff=destination,
                    payload="goods_cage",
                    dt=dispatch_time,
                    priority=priority,
                    task_type="waste_collection",
                )

    def _generate_specimens(self, day: datetime, is_weekend: bool) -> None:
        specimen_runs = 18 if not is_weekend else 10

        for _ in range(specimen_runs):
            source = random.choice(self.specimen_sources)
            dispatch_time = day.replace(hour=random.randint(6, 22), minute=random.randint(0, 59))
            priority = 27 if source in [
                "ICU-DH",
                "NEONATAL-DH",
                "BIRTHING-SUITE-DH",
                "UEC-DH",
                "SDEC-DH",
            ] else 21

            self.add_task(
                pickup=source,
                dropoff="RD",
                payload="drugs_box",
                dt=dispatch_time,
                priority=priority,
                task_type="specimen_run",
            )

    def _generate_kitchen_support(self, day: datetime) -> None:
        for dispatch_time in [day.replace(hour=6, minute=15), day.replace(hour=14, minute=45)]:
            self.add_task(
                pickup="KITCHEN",
                dropoff="KITCHEN-DH",
                payload="goods_cage",
                dt=dispatch_time,
                priority=14,
                task_type="kitchen_support",
            )

        for dispatch_time in [day.replace(hour=10, minute=30), day.replace(hour=18, minute=50)]:
            self.add_task(
                pickup="KITCHEN-DH",
                dropoff="RD2",
                payload="goods_cage",
                dt=dispatch_time,
                priority=15,
                task_type="waste_collection",
            )

    # --------------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------------
    def save_json(self, filepath: str | Path) -> None:
        filepath = Path(filepath)
        with filepath.open("w", encoding="utf-8") as file:
            json.dump(self.tasks, file, indent=2)

    def save_csv(self, filepath: str | Path) -> None:
        filepath = Path(filepath)
        with filepath.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "id",
                    "pickup",
                    "dropoff",
                    "payload",
                    "release_datetime",
                    "priority",
                ],
            )
            writer.writeheader()
            writer.writerows(self.tasks)

    def summary(self) -> dict:
        return {
            "total_tasks": len(self.tasks),
            "food_trolley": sum(1 for task in self.tasks if task["payload"] == "food_trolley"),
            "drugs_box": sum(1 for task in self.tasks if task["payload"] == "drugs_box"),
            "linen_cart": sum(1 for task in self.tasks if task["payload"] == "linen_cart"),
            "goods_cage": sum(1 for task in self.tasks if task["payload"] == "goods_cage"),
            "food_delivery": sum(1 for task in self.tasks if task["task_type"] == "food_delivery"),
            "empty_trolley_return": sum(1 for task in self.tasks if task["task_type"] == "empty_trolley_return"),
            "crockery_return": sum(1 for task in self.tasks if task["task_type"] == "crockery_return"),
            "drug_delivery": sum(1 for task in self.tasks if task["task_type"] == "drug_delivery"),
            "specimen_run": sum(1 for task in self.tasks if task["task_type"] == "specimen_run"),
            "linen_delivery": sum(1 for task in self.tasks if task["task_type"] == "linen_delivery"),
            "goods_delivery": sum(1 for task in self.tasks if task["task_type"] == "goods_delivery"),
            "waste_collection": sum(1 for task in self.tasks if task["task_type"] == "waste_collection"),
            "kitchen_support": sum(1 for task in self.tasks if task["task_type"] == "kitchen_support"),
        }


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main() -> None:
    generator = HospitalTaskGenerator()
    generator.generate(start_date=START_DATE, num_days=NUM_DAYS)

    generator.save_json("hospital_week_tasks_with_limits.json")
    # generator.save_csv("hospital_week_tasks_with_limits.csv")

    print(generator.summary())


if __name__ == "__main__":
    main()
