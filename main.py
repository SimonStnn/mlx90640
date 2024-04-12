import examples

from mlx90640 import utils


def main():
    addresses = [
        sensor["addr"] for sensor in utils.load_config("./config.json")["sensors"]
    ]
    # examples.console_example(addresses)
    # examples.heatmaps()
    examples.monitoring()


if __name__ == "__main__":
    main()
