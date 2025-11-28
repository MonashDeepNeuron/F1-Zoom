driver_to_team = {
    "VER": "Red Bull",
    "PER": "Red Bull",
    "HAM": "Mercedes",
    "RUS": "Mercedes",
    "LEC": "Ferrari",
    "SAI": "Ferrari",
    "NOR": "McLaren",
    "PIA": "McLaren",
    "ALO": "Aston Martin",
    "STR": "Aston Martin",
    "OCO": "Alpine",
    "GAS": "Alpine",
    "ALB": "Williams",
    "SAR": "Williams",
    "BOT": "Sauber",
    "ZHO": "Sauber",
    "MAG": "Haas",
    "HUL": "Haas",
    "TSU": "RB",
    "RIC": "RB"
}

def get_team_from_driver(driver_code: str) -> str:
    return driver_to_team.get(driver_code, "Unknown Team")