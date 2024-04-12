from typing import Any, Callable, TypedDict, Literal

from .frame import Frame, FrameValue

# "Alert" refers to Alert class, not a string
AlertCallback = Callable[["Alert", Frame], None]
Threshold = tuple[float, float]
ConditionCallback = Callable[..., bool]


class _Trigger(TypedDict):
    """
    Represents a trigger condition for alerts.

    Attributes:
        offender (Literal["min", "avg", "max", "cb"]): The type of value triggering the alert.
        value (FrameValue): The specific value that triggered the alert.
    """

    offender: Literal["min", "avg", "max", "cb"]
    """The type of value triggering the alert."""
    value: FrameValue
    """The specific value that triggered the alert."""


class Alert:
    """Represents an alert condition based on specified thresholds and custom conditions."""

    _trigger_count: int
    _last_trigger: _Trigger

    min_value: Threshold | float | None
    avg_value: Threshold | None
    max_value: Threshold | float | None
    condition_callback: ConditionCallback | None

    on_trigger: AlertCallback | None

    name: str

    def __init__(
        self,
        min_value: Threshold | float | None = None,
        avg_value: Threshold | None = None,
        max_value: Threshold | float | None = None,
        condition_callback: ConditionCallback | None = None,
        on_trigger: AlertCallback | None = None,
        *,
        name: str = "Alert",
    ) -> None:
        """
        Initialize an Alert object.

        Args:
            min_value (Threshold | float | None): Minimum threshold value.
            avg_value (Threshold | None): Average threshold value.
            max_value (Threshold | float | None): Maximum threshold value.
            condition_callback (ConditionCallback | None): User-defined condition check function.
            on_trigger (AlertCallback | None): Callback function when the alert is triggered.
            name (str, optional): Name of the alert (default: "Alert").
        """
        self._trigger_count = 0
        self.on_trigger = on_trigger

        self.min_value = min_value
        self.avg_value = avg_value
        self.max_value = max_value
        self.condition_callback = condition_callback

        self.name = name

    @property
    def trigger_count(self) -> int:
        """
        Returns the number of times the alert has been triggered for this instance (instance method).

        Returns:
            int: Instance-specific trigger count.
        """
        return self._trigger_count

    @property
    def last_trigger(self) -> _Trigger:
        """
        Get the last trigger condition.

        Returns:
            _Trigger: The last trigger condition.
        """
        return self._last_trigger

    def trigger_counter(func: Callable[..., Any], /) -> Callable[..., None]:  # type: ignore
        """Will increment the trigger count"""

        def wrap(self: "Alert", *args: Any, **kwargs: Any) -> None:
            self._trigger_count += 1
            func(self, *args, **kwargs)

        return wrap

    @trigger_counter
    def trigger(self, frame: Frame) -> None:
        """
        Triggers the alert based on the provided frame.

        Args:
            frame (Frame): Input frame for evaluation.
        """
        if self.on_trigger:
            self.on_trigger(self, frame)

    def evaluate(self, frame: Frame) -> None:
        """
        Evaluates the frame and triggers the alert if conditions are met.

        Args:
            frame (Frame): Input frame for evaluation.
        """
        if self.should_trigger(frame):
            self.trigger(frame)

    def should_trigger(self, frame: Frame) -> bool:
        """
        Determines whether the alert should be triggered based on the frame.

        Args:
            frame (Frame): Input frame for evaluation.

        Returns:
            bool: True if the alert should be triggered, False otherwise.
        """

        avg = frame.avg()
        if self.avg_value is not None and (
            self.avg_value[0] > avg or avg > self.avg_value[1]
        ):
            self._last_trigger = {"offender": "avg", "value": avg}
            return True

        for value in frame:
            if self._eval_min(value):
                self._last_trigger = {"offender": "min", "value": value}
                return True
            elif self._eval_max(value):
                self._last_trigger = {"offender": "max", "value": value}
                return True

        if self.condition_callback and self.condition_callback():
            self._last_trigger["offender"] = "cb"
            return True

        return False

    @staticmethod
    def _eval(
        test: Threshold | float | None,
        value: FrameValue,
        cb: Callable[[float, FrameValue], bool],
    ) -> bool:
        """
        Evaluate a condition based on the given test value and frame value.

        Args:
            test (Union[Threshold, float, None]): The test value or threshold.
            value (FrameValue): The frame value to evaluate.
            cb (Callable[[float, float], bool]): A callback function for custom evaluation.

        Returns:
            bool: True if the condition is met, False otherwise.
        """
        if test is None:
            return True
        elif isinstance(test, tuple):
            return test[0] <= value < test[1]
        return cb(test, value)

    def _eval_min(self, value: FrameValue) -> bool:
        """
        Evaluate whether the given value satisfies the minimum threshold condition.

        Args:
            value (FrameValue): The frame value to evaluate.

        Returns:
            bool: True if the value exceeds the minimum threshold, False otherwise.
        """
        return not Alert._eval(self.min_value, value, lambda test, value: value > test)

    def _eval_max(self, value: FrameValue) -> bool:
        """
        Evaluate whether the given value satisfies the maximum threshold condition.

        Args:
            value (FrameValue): The frame value to evaluate.

        Returns:
            bool: True if the value is above the maximum threshold, False otherwise.
        """
        return not Alert._eval(self.max_value, value, lambda test, value: value < test)
