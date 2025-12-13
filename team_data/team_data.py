def get_pitstop_data_per_race(session: int, race_name: str) -> pd.DataFrame:
    
    session = fastf1.get_session(year, race_name, "R")
    session.load()
    
    pitstops = session.get_pitstops()
    
    if pitstops is None or pitstops.empty:
        return pd.DataFrame()
    
    return pitstops

def get_dnf_data_per_race(season: int, race_name: str) -> pd.DataFrame:
    
    session = fastf1.get_session(season, race_name, "R")
    session.load()
    
    dnf = session.get_dnf()
    
    if dnf is None or dnf.empty:
        return pd.DataFrame()
        
    return dnf


if __name__ == "__main__":
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_colwidth', None)
    
    df1 = get_pitstop_data_per_race(2025, "Melbourne")
    
    print(df1)
    
    print("-------------------------------------------")
    
    df2 = get_dnf_data_per_race(2025, "Melbourne")
    
    print(df2)