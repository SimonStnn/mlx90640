import time
import datetime
import threading
import queue
from typing import Any, Generator, NoReturn
import matplotlib.pyplot as plt
import numpy as np

from mlx90640.alert import Alert
from mlx90640.driver import MLX90640
from mlx90640.frame import Frame
from mlx90640 import utils


def discover_evbs(addresses: list[int]) -> list[MLX90640]:
    devs: list[MLX90640] = []

    for addr in addresses:
        for _ in range(5):
            com = MLX90640.discover(addr)
            time.sleep(0.2)
            try:
                if com is None:
                    raise Exception(f"No COM found for {hex(addr)}")

                devs.append(MLX90640(com_port=com, i2c_addr=addr))
                print(f"Found {hex(addr)} on {com}")
                break
            except:
                pass
                print(f"No COM found for {hex(addr)}")
    return devs


def _capture_frame(dev: MLX90640) -> Generator[Frame, Any, NoReturn]:
    config = dev.config

    while True:
        frame = dev.capture(
            attempts=config["attempts"],
            threshold=config["threshold"],
            outlier_threshold=config["outlier_threshold"],
        )

        if frame is None:
            continue
        yield frame


def monitoring():
    config = MLX90640.load_config()
    addresses = [sensor["addr"] for sensor in config["sensors"]]
    devs = discover_evbs(addresses)

    frames_buffer: dict[int, Frame] = {}

    lock = threading.Lock()
    alert_queue: queue.Queue[tuple[MLX90640, Alert, Frame]] = queue.Queue()
    running = threading.Event()
    capture_threads: list[threading.Thread] = []

    # Add offsets to device
    for dev in devs:
        dev.temp_offset = dev.config["offset"]

        def alert_callback(alert: Alert, frame: Frame, dev: MLX90640 = dev):
            alert_queue.put((dev, alert, frame))

        dev.register_alert(
            Alert(
                min_value=0,
                max_value=38,
                on_trigger=alert_callback,
                name=f"{hex(dev.i2c_addr)} alert",
            )
        )

    def capture_frames(dev: MLX90640):
        capturer = _capture_frame(dev)
        while not running.is_set():
            frame = next(capturer)
            with lock:
                frames_buffer[dev.i2c_addr] = frame

    # Start a thread for each sensor
    for dev in devs:
        thread = threading.Thread(
            target=capture_frames,
            name=f"Captrure thread {hex(dev.i2c_addr)}",
            args=(dev,),
        )
        thread.start()
        capture_threads.append(thread)

    print("Monitoring...")
    while True:
        dev, alert, frame = alert_queue.get(block=True)
        print(
            " ".join(
                [
                    f"Alert '{alert.name}' triggered by {alert.last_trigger['offender']}",
                    f"with value {alert.last_trigger['value']:.2f}",
                    f"min: {frame.min()}, avg: {frame.avg()}, max: {frame.max()}",
                    f"({alert.trigger_count} triggers)",
                ]
            )
        )

        heatmap = np.array(
            [frame[i : i + frame.cols] for i in range(0, len(frame), frame.cols)]
        )
        frame_min = frame.min()
        frame_avg = frame.avg()
        frame_med = frame.med()
        frame_max = frame.max()

        plt.clf()
        im = plt.pcolormesh(heatmap, cmap="coolwarm")
        plt.colorbar(im)
        # Set title
        plt.title(f"Heatmap {hex(dev.i2c_addr)}")
        plt.xlabel(dev.name)

        # Add text below graph
        plt.text(
            1,
            1,
            "\n".join(
                [
                    f"max: {frame_max:.2f}°C",
                    f"avg: {frame_avg:.2f}°C",
                    f"med: {frame_med:.2f}°C",
                    f"min: {frame_min:.2f}°C",
                ]
            ),
            color="white",
            fontsize=10,
            bbox=dict(facecolor="black", alpha=0.25, linewidth=0, boxstyle="round"),
        )

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"alerts/heatmap_{dev.name}_{timestamp}.png"
        plt.savefig(filename, bbox_inches="tight")

    for thread in capture_threads:
        thread.join()


def console_example(addresses: list[int]):
    devs = discover_evbs(addresses)

    if len(devs) == 0:
        print("No devices, exiting...")
        return

    while True:
        print("---")
        for dev in devs:
            frame = dev.capture(threshold=(-40, 300))
            frame_avg = f"{frame.avg():>6.2f}" if frame else str(None).rjust(6)
            frame_min = f"{frame.min():>6.2f}" if frame else str(None).rjust(6)
            frame_max = f"{frame.max():>6.2f}" if frame else str(None).rjust(6)

            print(
                f"Sensor with addr {hex(dev.i2c_addr)} on {dev.com:<5} has min: {frame_min}, avg: {frame_avg}, max: {frame_max}"
            )

        print("---")
        time.sleep(1)


def heatmaps():
    config = MLX90640.load_config()
    addresses = [sensor["addr"] for sensor in config["sensors"]]
    devs = discover_evbs(addresses)

    frames_buffer: dict[int, Frame] = {}

    lock = threading.Lock()
    running = threading.Event()
    capture_threads: list[threading.Thread] = []

    def alert_callback(alert: Alert, frame: Frame):
        print(
            f"Alert '{alert.name}' triggered by {alert.last_trigger['offender']} with value {alert.last_trigger['value']:.2f} ({alert.trigger_count} triggers)"
        )

    # Add offsets to device
    for dev in devs:
        dev.temp_offset = dev.config["offset"]

        for i, alert in enumerate(dev.config["alerts"]):
            dev.register_alert(
                Alert(
                    min_value=alert["min"],
                    max_value=alert["max"],
                    on_trigger=alert_callback,
                    name=alert["name"] or f"{dev.name} alert ({i})",
                )
            )

    def capture_frames(dev: MLX90640):
        config = dev.config
        crop = config["crop"]
        penalty = (
            crop["penalty"]
            if "penalty" in crop and crop["penalty"] is not None
            else 100
        )
        capturer = _capture_frame(dev)
        while not running.is_set():
            frame = next(capturer)

            x1 = crop.get("x1") or 0
            y1 = crop.get("y1") or 0
            x2 = crop.get("x2") or frame.cols
            y2 = crop.get("y2") or frame.rows

            # Check if cropping is auto
            if ("col" in crop) and ("row" in crop):
                x1, y1, x2, y2 = utils.find_hottest_spot(frame, penalty)

            # print(f"Crop {hex(dev.i2c_addr)}: {x1=}, {y1=}, {x2=}, {y2=}\n", end="")

            frame = frame.crop(x1, y1, x2, y2)
            with lock:
                frames_buffer[dev.i2c_addr] = frame

    # Start a thread for each sensor
    for dev in devs:
        thread = threading.Thread(
            target=capture_frames,
            name=f"Captrure thread {hex(dev.i2c_addr)}",
            args=(dev,),
        )
        thread.start()
        capture_threads.append(thread)

    def on_close(event: Any):
        running.set()

    fig = plt.figure(num="Sensors")
    fig.canvas.mpl_connect("close_event", on_close)
    # plt.ion()
    while not running.is_set():
        plt.clf()

        with lock:
            frames_buffer_copy = frames_buffer.copy()

        for i, key in enumerate(sorted(frames_buffer_copy.keys())):
            frame = frames_buffer_copy[key]
            dev = [dev for dev in devs if dev.i2c_addr == key][0]
            config = dev.config

            # show_surfaces(frame)
            # continue

            heatmap = np.array(
                [frame[i : i + frame.cols] for i in range(0, len(frame), frame.cols)]
            )
            frame_min = frame.min()
            frame_avg = frame.avg()
            frame_med = frame.med()
            frame_max = frame.max()

            ax = plt.subplot(2, 3, i + 1)

            im = plt.pcolormesh(heatmap, cmap="coolwarm")
            fig.colorbar(im, ax=ax)

            # sns.heatmap(data=heatmap, cmap="coolwarm") # better but a lot slower

            # Hide x-axis and y-axis
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)

            # Set title
            plt.title(f"Heatmap {hex(dev.i2c_addr)}")

            # Add text below graph
            ax.text(
                1,
                1,
                "\n".join(
                    [
                        f"max: {frame_max:.2f}°C",
                        f"avg: {frame_avg:.2f}°C",
                        f"med: {frame_med:.2f}°C",
                        f"min: {frame_min:.2f}°C",
                    ]
                ),
                color="white",
                fontsize=10,
                bbox=dict(facecolor="black", alpha=0.25, linewidth=0, boxstyle="round"),
            )

        # Show the plots
        plt.tight_layout()  # Adjust spacing between subplots
        # plt.show(block=True)
        plt.pause(0.1)

    for thread in capture_threads:
        thread.join()


def show_surfaces(frame: Frame):
    """Demo"""

    config = utils.load_config("./config.json")
    crop = config["default"]["crop"]
    penalty: int = config["default"]["crop"]["penalty"]  # type: ignore

    x1 = crop.get("x1") or 0
    x2 = crop.get("x2") or frame.cols

    # Check if cropping is auto
    if ("col" in crop) and ("row" in crop):
        x1, _, x2, _ = utils.find_hottest_spot(frame, penalty)

    value1, value2 = x1, x2

    sequence = frame.get_row(12)
    # Create a signal (time series)
    signal = np.array(sequence).reshape(-1, 1)

    result = Frame.get_surfaces_edges(sequence, penalty, jump=1)
    x1, x2, _ = Frame.get_surfaces(sequence, result)

    # Plot the original signal and detected change points
    plt.figure(figsize=(10, 4))
    plt.plot(signal, label="Original Signal", color="blue")
    for cp in result:
        plt.axvline(x=cp, color="red", linestyle="--", label="Change Point")

    plt.axvline(x=value1, color="green", linestyle="--", label="Chosen surface")
    plt.axvline(x=value2, color="green", linestyle="--", label="Chosen surface")

    # plt.legend()
    plt.ylabel("Temp")
    plt.title("Change Point Detection")
    plt.show(block=True)

    # Print the detected change points
    print("Detected change points:", result)
