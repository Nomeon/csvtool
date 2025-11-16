import re
import os
import sys
import glob
import pandas as pd
from itertools import product

def resource_path(path: str) -> str:
    """Convert relative path to absolute path

    Args:
        path (str): Relative path

    Returns:
        str: Absolute path
    """    
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    complete_path = os.path.join(base_path, path)
    return complete_path


def get_input_list(path: str) -> list:
    """Gets all the CSV files from a directory.

    Args:
        path (str): The path to the directory.

    Returns:
        list: A list with all the IFC files.
    """
    return [csv for csv in glob.glob(f"{path}/*csv")]



def csv_to_df(file: str) -> pd.DataFrame:
    """Converts an Input CSV file to a dataframe.

    Args:
        file (str): The path to the Input CSV file.

    Returns:
        pd.DataFrame: The dataframe with all the parts.
    """

    df = pd.read_csv(file, sep=';')
    print(df)

    # Data preprocessing functions
    def fix_aantal(qty: str, unit: str) -> float:
        """Fix quantity values and handle unit conversions."""
        if pd.isna(qty):
            return 0.0
        qty_str = str(qty).replace(",", ".").split(" ")[0]
        try:
            qty_num = float(qty_str)
            # Temporary fix for m1 unit
            if unit == "m1":
                qty_num = qty_num / 1000
            return qty_num
        except (ValueError, TypeError):
            return 0.0

    def fix_dimensions(value) -> str:
        """Fix dimension values."""
        if pd.isna(value) or value == "":
            return "0.0"
        value_str = str(value).replace(",", ".").split(" ")[0]
        try:
            value_num = float(value_str)
            return f"{value_num:.1f}"
        except (ValueError, TypeError):
            return "0.0"

    def fix_weight(value, productcode: str) -> str:
        """Fix weight values with appropriate decimal precision."""
        if pd.isna(value) or value == "":
            return "0.0"
        value_str = str(value).replace(",", ".").split(" ")[0]
        try:
            value_num = float(value_str)
            # Determine decimal places (max 3)
            value_parts = str(value_num).split(".")
            decimals = min(len(value_parts[1]) if len(value_parts) > 1 else 0, 3)
            decimals = max(decimals, 1)  # At least 1 decimal

            fixed_value = f"{value_num:.{decimals}f}"

            # Debug logging for specific productcode
            if productcode == "C00012":
                print(f"Fixed weight: {value} -> {fixed_value}")

            return fixed_value
        except (ValueError, TypeError):
            return "0.0"

    # Apply preprocessing to DataFrame
    processed_df = pd.DataFrame()
    processed_df['Klant'] = df['Klant']
    processed_df['Projectnummer'] = df['Projectnummer']
    processed_df['Bouwnummer'] = df['Bouwnummer']
    processed_df['Moduletype'] = df['Moduletype']
    processed_df['Modulenaam'] = df['Modulenaam']
    processed_df['IFC-bestand'] = df['IFC-bestand']
    processed_df['Productcode'] = df['Productcode']
    processed_df['Productnaam'] = df['Productnaam']
    processed_df['Artikelcategorie'] = df['Artikelcategorie']
    processed_df['Dikte'] = df['Dikte'].apply(fix_dimensions)
    processed_df['Breedte'] = df['Breedte'].apply(fix_dimensions)
    processed_df['Lengte'] = df['Lengte'].apply(fix_dimensions)
    processed_df['Gewicht'] = df.apply(lambda row: fix_weight(row['Gewicht'], row['Productcode']), axis=1)
    processed_df['Materiaal'] = df['Materiaal']
    processed_df['Station'] = df['Station']
    processed_df['Aantal'] = df.apply(lambda row: fix_aantal(row['QTY'], row['Eenheid']), axis=1)
    processed_df['Eenheid'] = df['Eenheid']
    processed_df['Voorraad'] = df['Voorraad']

    return processed_df

def combine_dfs(df_list: list) -> pd.DataFrame:
    """Combines a list of dataframes to one dataframe.

    Args:
        df_list (list): A list with dataframes.

    Returns:
        pd.DataFrame: The combined dataframe.
    """
    df = pd.DataFrame()
    for dataframe in df_list:
        df = pd.concat([df, dataframe], ignore_index=True)

    df[["Dikte", "Breedte", "Lengte", "Gewicht", "Aantal"]] = df[
        ["Dikte", "Breedte", "Lengte", "Gewicht", "Aantal"]
    ].apply(pd.to_numeric)
    df = df.round({"Dikte": 1, "Lengte": 1, "Breedte": 1})
    df = df[~df['Station'].isin(['WS99', 'WS199'])]
    return df


def get_dikte(column: str) -> int:
    """Gets the dikte from the column.

    Args:
        column (str): The column.

    Returns:
        int: The dikte.
    """
    match = re.search(r"\d+", column)
    if match is None:
        print(f"Warning: No digits found in column name: '{column}'")
        return 0
    value = int(match.group())
    return value


def create_nesting(    
    combined_df: pd.DataFrame, prioriteit: pd.DataFrame
) -> dict:
    """Creates a dictionary with the nesting priority.

    Args:
        combined_df (pd.DataFrame): The dataframe with all the parts.
        prioriteit (pd.DataFrame): The dataframe with the priority of the modules.
        extended_prio (bool, optional): If the priority is extended. Defaults to False.

    Returns:
        dict: A dictionary with the nesting priority.
    """
    project = combined_df["Projectnummer"].iloc[0]
    bouwnummers = combined_df["Bouwnummer"].unique()
    mods = sorted(combined_df["Moduletype"].unique())
    sorted_werkstations = sorted(combined_df["Station"].unique())
    sorted_werkstations.reverse()
    mods.reverse()

    try:
        sorted_werkstations.append(
            sorted_werkstations.pop(sorted_werkstations.index("WS07"))
        )
    except:
        pass

    data, row = [], ""

    if prioriteit.empty:
        for bn, mt, ws in product(sorted(bouwnummers), mods, sorted_werkstations):
            row = f"{project}-{bn}-{mt}-{ws}"
            data.append({"Naam": row})
        
        for i in range(len(data)):
            data[i]["Prio"] = i
        df_prio = pd.DataFrame(data)
        prio_dict = dict(zip(df_prio.Naam, df_prio.Prio))
        return prio_dict

    modules = prioriteit.Condition.tolist()
    prioriteit["Value"] = pd.to_numeric(prioriteit["Value"])
    prio = dict(zip(prioriteit.Condition, prioriteit.Value))

    for bn, mt, ws in product(sorted(bouwnummers), modules, sorted_werkstations):
        row = f"{project}-{bn}-{mt}-{ws}"
        data.append({"Naam": row})

    df_prio = pd.DataFrame(data)
    df_prio["Prio"] = 0

    for index, row in df_prio.iterrows():
        for key, value in prio.items():
            for item in sorted_werkstations:
                key_ws = key + "-" + item
                ws_index = sorted_werkstations.index(item)
                if key_ws in row["Naam"]:
                    df_prio.loc[index, "Prio"] = (
                        (value - 1) + (ws_index * len(modules)) + 1
                    )

    prio_dict = dict(zip(df_prio.Naam, df_prio.Prio))
    return prio_dict

def bouwlaag_translation() -> dict:
    """Gives the dictionary to shorten the description of bouwlaag.

    Returns:
        dict: A dictionary with the translations.
    """
    bouwlaag_dict = {
        "Binnenwand - Beplating - Zijde 1": "BW - 1",
        "Gevel - Afwerking - Binnenzijde en Dagkant": "G - Dagkant",
        "Gevel - Beplating - Binnenzijde": "G - Binnenzijde",
        "Gevel - Installaties, Luchtdichting en Brandwerende Voorzieningen": "G - Inst, LD, BV",
        "Overig - Op Locatie": "O - Op locatie",
        "Plafond - Hoofdbalk Gevel 1e laag": "PL - HBG - 1",
        "Plafond - Hoofdbalk Gevel 2e laag": "PL - HBG - 2",
        "Plafond - Hoofdbalk Gevel 3e laag": "PL - HBG - 3",
        "Plafond - Hoofdbalk Woningscheiding 1e laag": "PL - HBW - 1",
        "Plafond - Hoofdbalk Woningscheiding 2e laag": "PL - HBW - 2",
        "Plafond - Hoofdbalk Woningscheiding 3e laag": "PL - HBW - 3",
        "Plafond - Randbalk Connectie 1e laag": "PL - RBC - 1",
        "Plafond - Randbalk Connectie 2e laag": "PL - RBC - 2",
        "Plafond - Randbalk Connectie 3e laag": "PL - RBC - 3",
        "Plafond - Randbalk Gevel 1e laag": "PL - RBG - 1",
        "Plafond - Randbalk Gevel 2e laag": "PL - RBG - 2",
        "Plafond - Randbalk Gevel 3e laag": "PL - RBG - 3",
        "Plafond - Randbalk Woningscheiding 1e laag": "PL - RBW - 1",
        "Plafond - Randbalk Woningscheiding 2e laag": "PL - RBW - 2",
        "Plafond en Plat Dak - Installaties en Brandwerende Voorzieningen": "PL + DAK - Inst",
        "Vloer - Beplating - Onderzijde": "VL - Onderzijde",
        "Vloer - Hoofdliggers en Subliggers en Elementen voor koppelen fundering": "VL - HL + SL",
        "Vloer - Installaties en Brandwerende Voorzieningen": "VL - Inst",
        "Vloer - Randbalk Connectie 1e laag": "VL - RBC - 1",
        "Vloer - Randbalk Connectie 2e laag": "VL - RBC - 2",
        "Vloer - Randbalk Gevel 1e laag": "VL - RBG - 1",
        "Vloer - Randbalk Gevel 2e laag": "VL - RBG - 2",
        "Vloer - Randbalk Gevel 3e laag": "VL - RBG - 3",
        "Woningscheidende wand - Installaties en Brandwerende Voorzieningen": "WSW - Inst",
    }
    return bouwlaag_dict


def custom_groupby(df, groupby_cols, sum_cols):
    """Custom groupby function for pandas.

    Args:
        df (pd.DataFrame): The dataframe.
        groupby_cols (list): The columns to group by.
        sum_cols (list): The columns to sum.

    Returns:
        pd.DataFrame: The grouped dataframe.
    """
    # Save original order of columns
    columns = df.columns.tolist()
    agg_dict = {}

    for col in sum_cols:
        agg_dict[col] = 'sum'

    for col in df.columns:
        if col not in sum_cols and col not in groupby_cols:
            agg_dict[col] = 'first'

    df_grouped = df.groupby(groupby_cols, as_index=False).agg(agg_dict)
    df_grouped = df_grouped[columns]

    return df_grouped