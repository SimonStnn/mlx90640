import json
from typing import Iterable, TypedDict

from .frame import Frame


class Crop(TypedDict):
    x1: int | None
    y1: int | None
    x2: int | None
    y2: int | None


class AutoCrop(Crop):
    col: int | None
    row: int | None
    penalty: int | None


class Alert(TypedDict):
    min: tuple[float, float] | float | None
    avg: tuple[float, float] | None
    max: tuple[float, float] | float | None
    name: str | None


class DefaultSensor(TypedDict):
    attempts: int
    crop: Crop | AutoCrop
    offset: float
    threshold: tuple[float, float]
    outlier_threshold: float
    alerts: list[Alert]


class Sensor(DefaultSensor):
    """Saved sensor in the config."""

    addr: int
    """I2C address of the sensor."""
    attempts: int
    """Times the program will attempt to read a valid frame"""
    crop: Crop | AutoCrop
    """How the program has to crop the frame"""
    offset: float
    """The program will add this offset to each read value from the frame."""
    threshold: tuple[float, float]
    """
    All values need to be within this threshold for a frame to be valid.
    
    If a frame is not valid it will not be passed to the rest of the 
    program, meaning it will be lost. The program will use another 
    attempt to read another frame.
    """
    outlier_threshold: float
    """
    The program will filter out some values that are way to high or to 
    low. This will filter out some potentially bad pixels. The bad pixels 
    will be replaces with the average value of the frame.
    """
    alerts: list[Alert]
    """List of alerts to be registered."""


class Config(TypedDict):
    default: DefaultSensor
    """Default values for a sensor"""
    sensors: list[Sensor]
    """List of sensors"""


_config: Config | None = None
"""
Private variable to store the loaded config.

This prevents to many read operations to the config file.
"""


def load_config(path: str) -> Config:
    """
    Load the config file from specified path.

    Config will be cached in memory. So the same config will be
    returned each time. Even if another path is specified the
    second time you call this method.
    """
    global _config
    # Return cached config
    if _config:
        return _config

    # Read config from file
    with open(path, "r", encoding="utf-8") as file:
        config: Config = json.loads(file.read())

    # Convert each sensor addr to int if its a hex string
    for i, _ in enumerate(config["sensors"]):
        sensor_addr = config["sensors"][i]["addr"]
        if isinstance(sensor_addr, str):
            config["sensors"][i]["addr"] = int(sensor_addr[2:], 16)

    config["default"].setdefault("crop", {"x1": 0, "y1": 0, "x2": 32, "y2": 24})

    # Convert threshold list to tuple[int, int]
    config["default"]["threshold"] = (
        config["default"]["threshold"][0],
        config["default"]["threshold"][1],
    )

    # Add None values for missing keys
    for sensor in config["sensors"]:
        sensor.setdefault("attempts", config["default"]["attempts"])
        sensor.setdefault("crop", config["default"]["crop"])
        sensor.setdefault("offset", config["default"]["offset"])
        sensor.setdefault("threshold", config["default"]["threshold"])
        sensor.setdefault("outlier_threshold", config["default"]["outlier_threshold"])
        sensor.setdefault("alerts", config["default"]["alerts"])

        for alert in sensor["alerts"]:
            alert.setdefault("min", None)
            alert.setdefault("avg", None)
            alert.setdefault("max", None)
            alert.setdefault("name", None)

    # Cache config
    _config = config
    return config


def calculate_best_coords_to_crop(
    sequences: Iterable[list[float]],
    penalty: int,
) -> tuple[int, int]:
    """
    Calculates the best coordinates for cropping based on sequences of values.

    Args:
        sequences (Iterable[list[float]]): An iterable of sequences (lists) of float values.
        penalty (int): A penalty value.

    Returns:
        tuple[int, int]: A tuple containing the best x-coordinate (min value) and the best y-coordinate (max value).
    """
    # Initialize variables to keep track of the best values and their indices
    best_value1 = []
    best_value2 = []

    # Iterate through the sequences
    for seq in sequences:
        edges = Frame.get_surfaces_edges(seq, penalty=penalty)
        value1, value2, _ = Frame.get_surfaces(seq, edges)
        if value1 != 0:
            best_value1.append(value1)
        if value2 != 32:
            best_value2.append(value2)

    return min(
        best_value1 if best_value1 else [0],
    ), max(
        best_value2 if best_value2 else [32],
    )


def find_hottest_spot(frame: Frame, penalty: int) -> tuple[int, int, int, int]:
    """
    Finds the hottest spot within a frame.

    Args:
        frame (Frame): The input frame.
        penalty (int): A penalty value to determine temperature differences.

    Returns:
        tuple[int, int, int, int]: A tuple containing the x1, y1, x2, and y2 coordinates of the hottest spot.
    """
    x1, x2 = calculate_best_coords_to_crop(frame.iterate_rows(), penalty)
    y1, y2 = calculate_best_coords_to_crop(
        (frame.get_col(i) for i in range(x1, x2)), penalty
    )
    return x1, y1, x2, y2
