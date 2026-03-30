from amr_sim_models import AMR, PayloadType


def loaded_power_w(amr: AMR, payload: PayloadType) -> float:
    if amr.payload_capacity_kg <= 0:
        return amr.motor_power_w
    load_fraction = min(1.0, max(0.0, payload.weight_kg / amr.payload_capacity_kg))
    return amr.motor_power_w * (1.0 + 0.35 * load_fraction)


def idle_move_power_w(amr: AMR) -> float:
    return amr.motor_power_w * 0.75


def energy_for_travel_kwh(power_w: float, duration_sec: float) -> float:
    return (power_w / 1000.0) * (duration_sec / 3600.0)


def total_route_energy_kwh(
    amr: AMR, payload: PayloadType, to_pickup_sec: float, loaded_sec: float
) -> float:
    return energy_for_travel_kwh(
        idle_move_power_w(amr), to_pickup_sec
    ) + energy_for_travel_kwh(loaded_power_w(amr, payload), loaded_sec)


def requires_recharge_before_route(amr: AMR, required_energy_kwh: float) -> bool:
    remaining_after_route = amr.battery_energy_kwh() - required_energy_kwh
    return remaining_after_route < amr.min_reserve_energy_kwh()
