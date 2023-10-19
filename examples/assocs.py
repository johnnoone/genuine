from __future__ import annotations

from dataclasses import dataclass

from genuine import build, define_factory, attributes_for


@dataclass
class Vehicle:
    brand: str
    motor: Motor


@dataclass
class Motor:
    fuel: str


with define_factory(model=Vehicle) as vehicle_factory:
    vehicle_factory.set("brand", "Mercedes")
    vehicle_factory.associate("motor", Motor)

with define_factory(model=Motor) as motor_factory:
    motor_factory.set("fuel", "unleaded petrol")


vehicle = build(Vehicle)
print(vehicle)


attrs = attributes_for(Vehicle)
print(attrs)
