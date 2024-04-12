import time
import serial
import mlx.mlx90640 as mlx
from mlx.hw_usb_evb90640 import HwUsbEvb90640, USB_PID, USB_VID

from .alert import Alert
from .frame import Frame
from . import utils

FRAME_RATE = 4.0

CONFIG_PATH = "./config.json"


class MLX90640:
    """
    Driver for MLX90640_evb_2.
    """

    Config = utils.Config

    sensors: list["MLX90640"] = []
    """List of sensors"""

    dev: mlx.Mlx9064x
    """
    Instance of the mlx.Mlx9064x class from the 
    [mlx9064x-driver](https://github.com/melexis-fir/mlx9064x-driver-py/tree/V1.3.0) 
    python package.
    """
    temp_offset: float
    """Offset that will be added to each value in a frame."""

    alerts: list[Alert]
    """List of registered alerts."""

    def __init__(
        self,
        *,
        com_port: str,
        i2c_addr: int = 0x33,
        frame_rate: float = FRAME_RATE,
        temp_offset: float = 0,
    ) -> None:
        # init serial coms with the sensor
        self.dev = mlx.Mlx9064x(com_port, i2c_addr, frame_rate)
        self.dev.init()

        self.temp_offset = temp_offset
        self.alerts = []

        # add self to sensor list
        MLX90640.sensors.append(self)

    @property
    def name(self) -> str:
        """Name of the device. The hexadecimal notation of its i2c address."""
        return hex(self.i2c_addr)

    @property
    def com(self) -> str:
        """Com port associated with the hardware."""
        return str(self.dev.hw.comport)  # type: ignore

    @property
    def i2c_addr(self) -> int:
        """I2C address of the device."""
        return self.dev.i2c_addr

    @property
    def frame_rate(self) -> float:
        """Frame rate of the device."""
        return float(self.dev.frame_rate)  # type: ignore

    @property
    def config(self) -> utils.Sensor:
        """The config for this device from the config file.

        *These values are not automatically stored in the MLX90640 instance."""
        return MLX90640.get_config(self.i2c_addr)

    @staticmethod
    def discover(i2c_addr: int) -> str | None:
        """
        Discover the I2C device with the specified address.

        Args:
            i2c_addr (int): The I2C address to search for.

        Returns:
            str | None: The COM port associated with the discovered device, or None if not found.
        """
        for com_port in HwUsbEvb90640.list_serial_ports(USB_PID, USB_VID):
            try:
                dev = MLX90640(com_port=com_port, i2c_addr=i2c_addr)
                dev.close()
                return dev.com
            except (OSError, serial.SerialException, ValueError, Exception):
                pass

    @staticmethod
    def load_config(path: str = CONFIG_PATH) -> utils.Config:
        """
        Loads the configuration file.

        Returns:
            Config: A Config object containing the sensor configuration.
        """
        return utils.load_config(path)

    @staticmethod
    def get_config(addr: int | str) -> utils.Sensor:
        """
        Retrieves the configuration for a specific sensor address.

        Args:
            addr (int | str): The sensor address (either an integer or a hexadecimal string, ex. 0x35).

        Returns:
            Sensor: A Sensor object with the sensor configuration.

        Raises:
            Exception: If the specified sensor address is not found in the configuration.
        """
        if isinstance(addr, str):
            addr = int(addr[2:], 16)

        config = MLX90640.load_config()
        sensor_config = next(
            (sensor for sensor in config["sensors"] if sensor["addr"] == addr), None
        )

        if sensor_config is None:
            raise Exception(
                f"Sensor {addr} not in config. Only available addresses are {', '.join([hex(sensor['addr']) for sensor in config['sensors']])}."
            )

        return sensor_config

    def capture(
        self,
        *,
        attempts: int = 10,
        threshold: tuple[float, float] = (-40.0, 300.0),
        outlier_threshold: float = 1.5,
    ) -> Frame | None:
        """
        Captures a frame from the device.

        Args:
            attempts (int, optional): The maximum number of attempts to capture a valid frame.
                Defaults to 10.

        Returns:
            Frame | None: The captured frame if successful, or None if no valid frame was obtained.
        """
        min_temp = threshold[0]
        max_temp = threshold[1]

        for _ in range(attempts):
            try:
                frame: Frame | None = self.dev.read_frame()  # type: ignore
                # In case EVB90640 hw is used, the EVB will buffer up to 4 frames, so possibly you get a cached frame.
                if frame is None:
                    continue
                # calculates the temperatures for each pixel
                compensated = Frame(self.dev.do_compensation(frame, add_ambient_temperature=False))  # type: ignore

                no_outliers = compensated.replace_outliers_with_average(
                    threshold=outlier_threshold,
                )

                final_frame = Frame([temp + self.temp_offset for temp in no_outliers])

                if all(min_temp <= temp <= max_temp for temp in final_frame):
                    # Handle registered alerts
                    self._handle_alerts(final_frame)
                    # Return the final frame
                    return final_frame
            except Exception:
                self.dev.clear_error(FRAME_RATE)

            # Small delay between frame reads
            time.sleep(0.01)
        # Frame failed to capture
        return None

    def _handle_alerts(self, frame: Frame) -> None:
        """
        Evaluate alerts for the given frame.

        Args:
            frame (Frame): A captured frame of the MLX90640.

        Returns:
            None
        """
        for alert in self.alerts:
            alert.evaluate(frame)

    def register_alert(self, alert: Alert) -> None:
        """
        Register an alert to be evaluated for future frames.

        Args:
            alert (Alert): An alert object to be registered.

        Returns:
            None
        """
        self.alerts.append(alert)

    def close(self):
        """Close serial communication with device."""
        try:
            self.dev.hw.channel.disconnect()  # type: ignore
        except:
            pass

    def __del__(self):
        self.close()

        if self in MLX90640.sensors:
            MLX90640.sensors.remove(self)
