"""
frame.py - Module for handling MLX90640 captured frames.

This module defines the `Frame` class, which represents a captured frame of the MLX90640 sensor.
The frame class inherits from list[float], meaning you can interpret an instance of 
this class as a simple list of floats
"""

import numpy as np
import ruptures as rpt

from typing import Any, overload, Iterable, Generator

FrameValue = float

FRAME_COLS = 32
FRAME_ROWS = 24


def avg(lst: list[float]) -> float:
    return sum(lst) / len(lst)


class Frame(list[FrameValue]):
    """Representation of a captured frame of the MLX90640"""

    cols: int
    rows: int

    def __init__(
        self,
        iterable: Iterable[FrameValue],
        cols: int = FRAME_COLS,
        rows: int = FRAME_ROWS,
    ) -> None:
        """
        Initialize a Frame object.

        Args:
            iterable (Iterable[FrameValue]): An iterable of frame values.
            cols (int, optional): Number of columns (default: 32).
            rows (int, optional): Number of rows (default: 24).

        Raises:
            ValueError: If the dimensions of the object do not match the expected size.
        """
        self.cols = cols
        self.rows = rows
        super().__init__(iterable)

        if len(self) != self.cols * self.rows:
            raise ValueError(
                "The dimensions of the object do not match the expected size."
            )

    @property
    def is_modified(self):
        """
        Check if the dimensions of the frame have been modified from the original size.

        Returns:
            bool: True if the frame dimensions differ from the expected size, False otherwise.
        """
        return self.cols != FRAME_COLS or self.rows != FRAME_ROWS

    def iterate_cols(self) -> Generator[list[FrameValue], Any, None]:
        """
        Generator function to iterate over each column in the frame.

        Yields:
            list[FrameValue]: A column from the frame.
        """
        for col in range(self.cols):
            yield self.get_col(col)

    def iterate_rows(self) -> Generator[list[FrameValue], Any, None]:
        """
        Generator function to iterate over each row in the frame.

        Yields:
            list[FrameValue]: A row from the frame.
        """
        for row in range(self.rows):
            yield self.get_row(row)

    @staticmethod
    def get_surfaces_edges(
        sequence: list[FrameValue], penalty: int, jump: int = 5, model: str = "l2"
    ) -> list[int]:
        """
        Detect change points in a sequence of frame values.

        Args:
            sequence (list[FrameValue]): A list of frame values.
            penalty (int): Penalty parameter for change point detection.
            jump (int, optional): Jump parameter (default: 5).
            model (str, optional): Change point detection model (default: "l2").

        Returns:
            list[int]: List of detected change points.
        """
        # Create a signal (time series)
        signal = np.array(sequence).reshape(-1, 1)

        # Initialize the change point detector
        algo = rpt.Pelt(model, jump=jump).fit(signal)

        # Detect change points
        result: list[int] = algo.predict(penalty)

        return [0, *result]

    @staticmethod
    def get_surfaces(
        sequence: list[FrameValue], edges: list[int]
    ) -> tuple[int, int, list[FrameValue]]:
        """Get the surface with the highest average value in a given sequence."""
        surfaces = []
        highest = [min(sequence)]
        start, end = 0, 0
        for i in range(len(edges) - 1):
            surface = sequence[edges[i] : edges[i + 1]]
            surfaces.append(surface)
            if avg(surface) > avg(highest):
                highest = surface
                start, end = edges[i], edges[i + 1]

        return start, end, highest

    def min(self) -> FrameValue:
        return min(self)

    def avg(self) -> float:
        return avg(self)

    def med(self) -> float:
        """Calculates the median value of a list of floats."""
        s = sorted(self)
        n = len(s)
        return (s[n // 2] + s[(n - 1) // 2]) / 2 if n % 2 == 0 else s[n // 2]

    def max(self) -> FrameValue:
        return max(self)

    def replace_outliers_with_average(self, threshold: float = 2) -> "Frame":
        """
        Replaces outliers in a list with the average of non-outlier values.

        Args:
            threshold (float): Threshold for identifying outliers (default: 2).

        Returns:
            list: A new list with outliers replaced.
        """
        # Calculate the average of non-outlier values
        frame_avg = self.avg()
        non_outliers = [
            x if abs(x - frame_avg) < threshold * frame_avg else frame_avg for x in self
        ]
        return Frame(non_outliers)

    @overload
    def crop(self, coords1: tuple[int, int], coords2: tuple[int, int]) -> "Frame": ...

    @overload
    def crop(self, x1: int, y1: int, x2: int, y2: int) -> "Frame": ...

    def crop(self, *args: Any, **kwargs: Any) -> "Frame":
        """
        Crops a frame.

        Frame needs to be unmodified. (24x32)

        Returns:
            Frame: A new cropped frame.
        """

        if len(args) == 2:
            coords1, coords2 = args
            x1, y1 = coords1
            x2, y2 = coords2
        else:
            x1, y1, x2, y2 = args

        x1 = max(0, x1)
        x2 = min(FRAME_COLS, x2)
        y1 = max(0, y1)
        y2 = min(FRAME_ROWS, y2)

        return Frame(
            [self[(i * 32) + j] for i in range(y1, y2) for j in range(x1, x2)],
            x2 - x1,
            y2 - y1,
        )

    def get_index(self, row: int, col: int) -> int:
        """
        Calculates the linear index corresponding to a given row and column in a 2D grid.

        Args:
            row (int): The row index (0-based).
            col (int): The column index (0-based).

        Returns:
            int: The linear index obtained by multiplying the row index by the number of columns
                and adding the column index.

        Raises:
            IndexError: If either the row or column index is out of bounds.
        """
        if not (0 <= row <= self.rows):
            raise IndexError(
                f"Row index out of bounds. Received {row}, max is {self.rows}"
            )
        elif not (0 <= col <= self.cols):
            raise IndexError(
                f"Column index out of bounds. Received {col}, max is {self.cols}"
            )
        return row * self.cols + col

    def get_row(self, row: int) -> list[FrameValue]:
        """
        Get a specific row from the frame.

        Args:
            row (int): Row index.

        Returns:
            list[FrameValue]: List of frame values in the specified row.
        """
        return [self[self.get_index(row, col)] for col in range(self.cols)]

    def get_col(self, col: int) -> list[FrameValue]:
        """
        Get a specific column from the frame.

        Args:
            col (int): Column index.

        Returns:
            list[FrameValue]: List of frame values in the specified column.
        """
        return [self[self.get_index(row, col)] for row in range(self.rows)]
