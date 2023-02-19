
import argparse
import asyncio
import logging

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from datadog import initialize, statsd

logger = logging.getLogger(__name__)
initialize(statsd_host="datadog-agent", statsd_port=8125)

ATC_SERVICE_DATA_KEY = "0000181a-0000-1000-8000-00805f9b34fb"

def simple_callback(device: BLEDevice, advertisement_data: AdvertisementData):
    service_data = advertisement_data.service_data.get(ATC_SERVICE_DATA_KEY)
    if not service_data:
        return

    mac_address = service_data[0:6].hex(':').upper()
    temperature = (int(service_data[6]) * 256 + int(service_data[7])) / 10
    humidity_percent = int(service_data[8])
    battery_percent = int(service_data[9])
    packet_count = int(service_data[12])
    logger.info("%s[%s]: Temp=%.1f Humidity=%d%% Battery=%d%% #%d", mac_address, device.name, temperature, humidity_percent, battery_percent, packet_count)
    metric_tags = ['city:paris', 'home:fmaison', 'device_name:%s' % device.name, 'mac_address:%s' % mac_address)
    statsd.gauge('thermometer.temperature', temperature, tags=metric_tags)
    statsd.gauge('thermometer.humidity', humidity_percent, tags=metric_tags)
    statsd.gauge('thermometer.battery', battery_percent, tags=metric_tags)




async def main(args: argparse.Namespace):
    scanner = BleakScanner(
        simple_callback, args.services, cb=dict(use_bdaddr=args.macos_use_bdaddr)
    )

    while True:
        logger.info("(re)starting scanner")
        await scanner.start()
        await asyncio.sleep(60.0)
        await scanner.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--macos-use-bdaddr",
        action="store_true",
        help="when true use Bluetooth address instead of UUID on macOS",
    )

    parser.add_argument(
        "--services",
        metavar="<uuid>",
        nargs="*",
        help="UUIDs of one or more services to filter for",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="sets the logging level to debug",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
    )

    asyncio.run(main(args))
