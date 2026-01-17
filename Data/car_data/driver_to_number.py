driver_to_number = {
    "VER": 1,
    "PER": 11,
    "HAM": 44,
    "RUS": 63,
    "LEC": 16,
    "SAI": 55,
    "NOR": 4,
    "PIA": 81,
    "ALO": 14,
    "STR": 18,
    "OCO": 31,
    "GAS": 10,
    "ALB": 23,
    "SAR": 2,
    "BOT": 77,
    "ZHO": 24,
    "MAG": 20,
    "HUL": 27,
    "TSU": 22,
    "RIC": 3,
    "BOR": 5,
    "COL": 43
}

def get_number_from_driver(driver_code: str) -> int:
    return driver_to_number.get(driver_code, -1)

def get_driver_from_number(driver_number: int) -> str:
    for driver, number in driver_to_number.items():
        if number == driver_number:
            return driver
    return "Unknown Driver"