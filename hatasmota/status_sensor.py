"""Tasmota status sensor."""
import json
import logging

import attr

from .const import CONF_DEVICENAME, CONF_MAC, SENSOR_STATUS_IP, SENSOR_STATUS_SIGNAL
from .entity import (
    TasmotaAvailability,
    TasmotaAvailabilityConfig,
    TasmotaEntity,
    TasmotaEntityConfig,
)
from .utils import (
    config_get_state_offline,
    config_get_state_online,
    get_topic_command_status,
    get_topic_stat_status,
    get_topic_tele_state,
    get_topic_tele_will,
    get_value_by_path,
)

_LOGGER = logging.getLogger(__name__)

# 14:45:37 MQT: tasmota_B94927/tele/HASS_STATE = {
#  "Version":"9.0.0.1(tasmota)",               stat/STATUS2:"StatusFWR"."Version"
#  "BuildDateTime":"2020-10-08T21:38:21",      stat/STATUS2:"StatusFWR"."BuildDateTime"
#  "Module or Template":"Generic",             <NONE>
#  "RestartReason":"Software/System restart",  stat/STATUS1:"StatusPRM"."RestartReason"
#  "Uptime":"1T17:04:28",                      stat/STATUS11:"StatusSTS"."Uptime"; tele/STATE:"Uptime"
#  "Hostname":"tasmota_B94927",                stat/STATUS5:"StatusNET":"Hostname"
#  "IPAddress":"192.168.0.114",                stat/STATUS5:"StatusNET":"IPAddress"
#  "RSSI":"100",                               stat/STATUS11:"StatusSTS":"RSSI"; tele/STATE:"RSSI"
#  "Signal (dBm)":"-49",                       stat/STATUS11:"StatusSTS":"Signal"; tele/STATE:"Signal"
#  "WiFi LinkCount":1,                         stat/STATUS11:"StatusSTS":"LinkCount"; tele/STATE:"LinkCount"
#  "WiFi Downtime":"0T00:00:03",               stat/STATUS11:"StatusSTS":"Downtime"; tele/STATE:"Downtime"
#  "MqttCount":1,                              stat/STATUS11:"StatusSTS":"MqttCount"; tele/STATE:"MqttCount"
#  "LoadAvg":19                                stat/STATUS11:"StatusSTS":"LoadAvg"; tele/STATE:"LoadAvg"
# }

SENSORS = [SENSOR_STATUS_IP, SENSOR_STATUS_SIGNAL]

NAMES = {
    SENSOR_STATUS_SIGNAL: "Signal",
    SENSOR_STATUS_IP: "IP",
}

STATE_PATHS = {
    SENSOR_STATUS_SIGNAL: ["Wifi", "Signal"],
}

STATUS_PATHS = {
    SENSOR_STATUS_SIGNAL: ["StatusSTS", "Wifi", "Signal"],
    SENSOR_STATUS_IP: ["StatusNET", "IPAddress"],
}

STATUS_TOPICS = {
    SENSOR_STATUS_SIGNAL: 11,
    SENSOR_STATUS_IP: 5,
}

QUANTITY = {
    SENSOR_STATUS_SIGNAL: SENSOR_STATUS_SIGNAL,
    SENSOR_STATUS_IP: None,
}

UNITS = {
    SENSOR_STATUS_SIGNAL: "dB",
    SENSOR_STATUS_IP: None,
}


@attr.s(slots=True, frozen=True)
class TasmotaStatusSensorConfig(TasmotaAvailabilityConfig, TasmotaEntityConfig):
    """Tasmota switch configuation."""

    poll_topic: str = attr.ib()
    sensor: str = attr.ib()
    state_topic: str = attr.ib()
    status_topic: str = attr.ib()

    @classmethod
    def from_discovery_message(cls, config, platform):
        """Instantiate from discovery message."""
        sensors = [
            cls(
                endpoint="status_sensor",
                idx=None,
                friendly_name=f"{config[CONF_DEVICENAME]} {NAMES[sensor]}",
                mac=config[CONF_MAC],
                platform=platform,
                poll_payload="0",
                poll_topic=get_topic_command_status(config),
                availability_topic=get_topic_tele_will(config),
                availability_offline=config_get_state_offline(config),
                availability_online=config_get_state_online(config),
                sensor=sensor,
                state_topic=get_topic_tele_state(config),
                status_topic=get_topic_stat_status(config, STATUS_TOPICS[sensor]),
            )
            for sensor in SENSORS
        ]
        return sensors

    @property
    def unique_id(self):
        """Return unique_id."""
        return f"{self.mac}_{self.platform}_{self.endpoint}_{self.sensor}"


class TasmotaStatusSensor(TasmotaAvailability, TasmotaEntity):
    """Representation of a Tasmota switch."""

    def __init__(self, **kwds):
        """Initialize."""
        self._sub_state = None
        self._attributes = {}
        super().__init__(**kwds)

    async def subscribe_topics(self):
        """Subscribe to topics."""

        def state_message_received(msg):
            """Handle new MQTT state messages."""
            try:
                payload = json.loads(msg.payload)
            except (json.decoder.JSONDecodeError):
                return

            state = None
            if msg.topic == self._cfg.state_topic:
                state = get_value_by_path(payload, STATE_PATHS[self._cfg.sensor])
            else:
                state = get_value_by_path(payload, STATUS_PATHS[self._cfg.sensor])
            if state is not None:
                self._on_state_callback(state)

        availability_topics = self.get_availability_topics()
        topics = {}
        if self._cfg.sensor in STATE_PATHS:
            # Periodic state update (tele/STATE)
            topics["state_topic"] = {
                "event_loop_safe": True,
                "topic": self._cfg.state_topic,
                "msg_callback": state_message_received,
            }
        # Polled state update (stat/STATUS#)
        topics["status_topic"] = {
            "event_loop_safe": True,
            "topic": self._cfg.status_topic,
            "msg_callback": state_message_received,
        }
        topics = {**topics, **availability_topics}

        self._sub_state = await self._mqtt_client.subscribe(
            self._sub_state,
            topics,
        )

    async def unsubscribe_topics(self):
        """Unsubscribe to all MQTT topics."""
        self._sub_state = await self._mqtt_client.unsubscribe(self._sub_state)

    @property
    def quantity(self):
        """Return the sensor's quantity (speed, mass, etc.)."""
        return QUANTITY[self._cfg.sensor]

    @property
    def unit(self):
        """Return the unit this state is expressed in."""
        return UNITS[self._cfg.sensor]
