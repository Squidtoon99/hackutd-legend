from dataclasses import dataclass
from typing import Dict


@dataclass
class ServerInfo:
	name: str
	tempC: int
	jira: str
	uptime: str


# Mock mapping from AprilTag id -> server info
MOCK_SERVERS: Dict[int, ServerInfo] = {
	1: ServerInfo(name="Rack A12 - Srv 01", tempC=31, jira="SCRUM-1001", uptime="27d 4h"),
	2: ServerInfo(name="Rack A12 - Srv 02", tempC=28, jira="SCRUM-1002", uptime="14d 2h"),
	3: ServerInfo(name="Rack B03 - Srv 15", tempC=33, jira="SCRUM-1003", uptime="5d 22h"),
	4: ServerInfo(name="Rack B03 - Srv 16", tempC=29, jira="SCRUM-1004", uptime="9d 6h"),
	5: ServerInfo(name="Rack C07 - Srv 03", tempC=27, jira="SCRUM-1005", uptime="42d 18h"),
	6: ServerInfo(name="Rack C07 - Srv 04", tempC=35, jira="SCRUM-1006", uptime="1d 3h"),
	7: ServerInfo(name="Rack D22 - Srv 08", tempC=32, jira="SCRUM-1007", uptime="11d 9h"),
	8: ServerInfo(name="Rack D22 - Srv 09", tempC=26, jira="SCRUM-1008", uptime="73d 1h"),
	9: ServerInfo(name="Rack E05 - Srv 12", tempC=30, jira="SCRUM-1009", uptime="18d 21h"),
	10: ServerInfo(name="Rack E05 - Srv 13", tempC=34, jira="SCRUM-1010", uptime="6d 7h"),
	11: ServerInfo(name="Rack F10 - Srv 20", tempC=25, jira="SCRUM-1011", uptime="3d 12h"),
	12: ServerInfo(name="Rack F10 - Srv 21", tempC=36, jira="SCRUM-1012", uptime="27d 16h"),
	13: ServerInfo(name="Rack G01 - Srv 02", tempC=28, jira="SCRUM-1013", uptime="95d 4h"),
	14: ServerInfo(name="Rack G01 - Srv 03", tempC=37, jira="SCRUM-1014", uptime="12d 2h"),
	15: ServerInfo(name="Rack H18 - Srv 11", tempC=24, jira="SCRUM-1015", uptime="54d 8h"),
	16: ServerInfo(name="Rack H18 - Srv 12", tempC=39, jira="SCRUM-1016", uptime="0d 20h"),
}


