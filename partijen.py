import pandas as pd
import numpy as np
import helpers

def BB(df: pd.DataFrame, ordernummer: str, path: str, prio_dict: dict, bulk_file: list, bulk: bool) -> None:
    """Gets the BB parts from the dataframe and saves it to a CSV file.

    Args:
        df (pd.DataFrame): The dataframe with all the parts.
        ordernummer (str): The ordernumber of the project.
        path (str): The path to save the CSV file.
        prio_dict (dict): The dictionary with the priority of the modules.
        bulk (list): The dataframe with all the parts for the bulk CSV.
    """
    project, bouwnummer = df["Projectnummer"].iloc[0], df["Bouwnummer"].iloc[0]

    # Filter for materials that go to milling companies
    df = df[df["Materiaal"].str.contains("LVLQ|LVLS|CEM|SPANO|PRO|MDF", case=False, na=False)]
    df = df[df["Productnaam"].str.contains("LVLQ 90|LVLQ 100|LVLQ 144|LVLQ 69") |
        ((df["Productnaam"].str.contains("LVLS 45")) & (df["Lengte"] > 3360)) |
        ((df["Productnaam"].str.contains("SPANO 18")) & (df["Lengte"] > 2700)) |
        df["Materiaal"].str.contains("BAUB")]

    if df.empty:
        return

    df = df.astype({"Aantal": "int"})
    df = df.groupby(df.columns.tolist(), as_index=False, dropna=False).size()
    df["Aantal"] = (df["Aantal"] * df["size"]).astype(int)
    df = df.drop("size", axis=1)

    df["Nesting Prioriteit"] = df["Moduletype"]
    modules = sorted(df["Moduletype"].unique())
    prioriteit = dict(zip(modules, [x for x in range(len(modules), 0, -1)]))
    df = df.replace({"Nesting Prioriteit": prioriteit})

    df[["CNC Bewerking", "InkooporderNr"]] = "", ordernummer

    df["Prio"] = df["Modulenaam"] + "-" + df["Station"]
    for key, value in prio_dict.items():
        df.loc[df["Prio"].str.contains(key, na=False), "Nesting Prioriteit"] = value

    df = df[
        [
            "Materiaal",
            "Productcode",
            "Productnaam",
            "Dikte",
            "Aantal",
            "CNC Bewerking",
            "Modulenaam",
            "InkooporderNr",
            "Nesting Prioriteit",
            "Station",
        ]
    ]
    df = df.rename(
        columns={
            "Materiaal": "Materiaal BB",
            "Productnaam": "OnderdeelNaam",
            "Dikte": "Dikte BB",
            "Aantal": "Aantal BB",
        }
    )
    df = df.sort_values(by=["OnderdeelNaam", "Modulenaam"])

    # Normaal-Normaal, bulk = False and casettes = False, BN
    if not bulk:
        df = df[~df["Productcode"].isin(bulk_file)]
        df.to_csv(f"{path}/{ordernummer}-{project}-{bouwnummer}-BB.csv", index=False, sep=";")

    # Normaal-Bulk, bulk = True and casettes = False, BATCH
    elif bulk:
        df_bulk = df[df["Productcode"].isin(bulk_file)]
        if not df_bulk.empty:
            df_bulk.to_csv(f"{path}/{ordernummer}-{project}-BB-BULK.csv", index=False, sep=";")


def VH(df: pd.DataFrame, ordernummer: str, path: str, prio_dict: dict, bulk_file: list,  meterkast_file: list, bulk: bool, meterkast: bool=False) -> None:
    """Gets the Van Hulst parts from the dataframe and saves it to a CSV file.

    Args:
        df (pd.DataFrame): The dataframe with all the parts.
        ordernummer (str): The ordernumber of the project.
        path (str): The path to save the CSV file.
        prio_dict (dict): The dictionary with the priority of the modules.
    """
    project, bouwnummer = df["Projectnummer"].iloc[0], df["Bouwnummer"].iloc[0]

    bouwnummer = df["Bouwnummer"].iloc[0]
    bouwnummer_kort = bouwnummer
    if bouwnummer.startswith("BN"):
        bouwnummer_kort = bouwnummer.replace("BN", "")

    # Filter for materials that go to milling companies
    df = df[df["Materiaal"].str.contains("LVLQ|LVLS|CEM|SPANO|PRO|MDF", case=False, na=False)]
    df = df[~(df["Productnaam"].str.contains("LVLQ 90|LVLQ 100|LVLQ 144|LVLQ 69") | ((df["Productnaam"].str.contains("LVLS 45")) & (df["Lengte"] > 3360)) | ((df["Productnaam"].str.contains("SPANO 18")) & (df["Lengte"] > 2700)) | df["Materiaal"].str.contains("BAUB"))]
    df = df[~df["Materiaal"].str.contains("PRO|FERM")]

    if df.empty:
        return

    df["InkooporderNr"] = f"{ordernummer}-{bouwnummer_kort}"
    df["Klant"] = f"geWOONhout {project} {bouwnummer}"
    df["Order"] = (
        str(project)
        + " "
        + str(bouwnummer)
        + " "
        + df["Materiaal"]
        + " "
        + df["Dikte"].astype(int).astype(str)
    )
    df["Bestand"] = (
        "P:\\"
        + str(project)
        + "\\STP\\"
        + df["Productcode"]
        + ".ipt.stp"
    )
    df[
        [
            "Configuratie",
            "Setup",
            "Nesten",
            "Nest Rotatie Methode",
            "Nest Rotatie",
            "Nest Setnr",
        ]
    ] = ("", "", 1, 0, 180, 1)
    df["Index.1"] = df.index
    df = df.astype({"Aantal": int, "Dikte": int})
    df["Nesting Prioriteit"] = df["Moduletype"]
    # Barcode met cijfers, WS weghalen
    df["Barcode"] = (
        df["Productcode"]
        + "-"
        + df["Station"].str[-2:]
        + "-"
        + df["Moduletype"].str[-2:]
    )
    df = df.groupby(["Barcode"], as_index=False).agg(
        dict(
            map(
                (lambda x: (x, "sum") if x == "Aantal" else (x, "first")),
                df.columns.tolist(),
            )
        )
    )

    df["Prio"] = df["Modulenaam"] + "-" + df["Station"]
    for key, value in prio_dict.items():
        df.loc[df["Prio"].str.contains(key, na=False), "Nesting Prioriteit"] = value

    df = df[
        [
            "Klant",
            "Order",
            "InkooporderNr",
            "Configuratie",
            "Setup",
            "Materiaal",
            "Dikte",
            "Bestand",
            "Productnaam",
            "Aantal",
            "Nesten",
            "Nest Rotatie Methode",
            "Nest Rotatie",
            "Nesting Prioriteit",
            "Nest Setnr",
            "Station",
            "Productcode",
            "Modulenaam",
            "Barcode",
        ]
    ]

    df = df.rename(
        columns={
            "Klant": "KlantvH",
            "Materiaal": "Materiaal vH",
            "Dikte": "Dikte vH",
            "Aantal": "AantalvH",
            "Productnaam": "OnderdeelNaam",
        }
    )

    # Add WS to order number if CEM10, SPANO 10, SPANO 18
    df.loc[df['Order'].str.contains('CEM10|SPANO 10|SPANO 18', na=False), 'Order'] = df['Order'] + '-' + df['Station']
    
    # Add WS101WS102 to LVLS 45 if station is WS101 or WS102
    df.loc[df['Order'].str.contains('LVLS 45', na=False) & df['Station'].isin(['WS101', 'WS102']), 'Order'] = df['Order'] + '-WS101WS102'

    # Add -BW to the order number for binnenwanden, checken of dit mag voor alles.
    mask = (
        (df["Materiaal vH"] == "LVLS")
        & (df["Dikte vH"] == 45)
        & df["Station"].isin(["WS05", "WS114"])
    )

    df_rest = df[~mask]
    df_binnenwand = df[mask]
    df_binnenwand["Order"] += "-BW"
    df = pd.concat([df_rest, df_binnenwand], ignore_index=True, sort=False)

    # Convert modulenaam to string:
    df['Modulenaam'] = df['Modulenaam'].astype(str)

    # Meterkast CSV
    df_meterkast = df[df["Productcode"].isin(meterkast_file)]
    df = df[~df["Productcode"].isin(meterkast_file)]
    if not df_meterkast.empty and meterkast:
        df_meterkast.to_csv(f"{path}/{ordernummer}-{project}-VH-METERKAST.csv", index=False, sep=";")
        
    if bulk:
        df_bulk = df[df["Productcode"].isin(bulk_file)]
        df_bulk["Modulenaam"] = str(project) + "-BULK"
        if not df_bulk.empty:
            df_bulk = helpers.custom_groupby(df_bulk, ["Order", "OnderdeelNaam", "Productcode"], ["AantalvH"])
            df_bulk.to_csv(f"{path}/{ordernummer}-{project}-VH-BULK.csv", index=False, sep=";")
    else:
        df = df[~df["Productcode"].isin(bulk_file)]
        
        # Split it on deel 1 and deel 2 based on the following rules:
        # - up to and including WS106 -> deel 1
        # - from WS107 and higher -> deel 2
        # - Name contains LVLS 63, LVLQ 21, LVLQ 75, MDF 18, MDFO 18 -> deel 1
        deel1_conditions = (df["Station"].str.extract(r'WS(\d+)', expand=False).astype(float) <= 106) | df["OnderdeelNaam"].str.contains("LVLS 63|LVLQ 21|LVLQ 75|MDF 18|MDFO 18", na=False)
        df_deel1 = df[deel1_conditions]
        df_deel2 = df[~deel1_conditions]
        if not df_deel1.empty:
            df_deel1 = helpers.custom_groupby(df_deel1, ["Order", "OnderdeelNaam", "Productcode"], ["AantalvH"])
            df_deel1.to_csv(f"{path}/{ordernummer}-{project}-{bouwnummer_kort}-VH-1.csv", index=False, sep=";")
        if not df_deel2.empty:
            df_deel2 = helpers.custom_groupby(df_deel2, ["Order", "OnderdeelNaam", "Productcode"], ["AantalvH"])
            df_deel2.to_csv(f"{path}/{ordernummer}-{project}-{bouwnummer_kort}-VH-2.csv", index=False, sep=";")
        

def VMG(df: pd.DataFrame, ordernummer: str, path: str, prio_dict: dict, bulk_file: list, bulk: bool) -> None:
    """Gets the VMG parts from the dataframe and saves it to a CSV file.

    Args:
        df (pd.DataFrame): The dataframe with all the parts.
        ordernummer (str): The ordernumber of the project.
        path (str): The path to save the CSV file.
        prio_dict (dict): The dictionary with the priority of the modules.
    """
    project, bouwnummer = df["Projectnummer"].iloc[0], df["Bouwnummer"].iloc[0]
    df = df[df["Materiaal"].str.contains("PRO|FERM")]

    if df.empty:
        return
    
    df["Nesting Prioriteit"] = df["Moduletype"]
    df["Prio"] = df["Modulenaam"] + "-" + df["Station"]
    for key, value in prio_dict.items():
        df.loc[df["Prio"].str.contains(key, na=False), "Nesting Prioriteit"] = value
    
    df['Bouwlaag promat'] = ''

    # If BuildingStep row is not empty, split the string and get the bouwlaag
    for index, row in df.iterrows():
        if row['BuildingStep'] == '':
            continue
        df.at[index, 'Bouwlaag promat'] = row['BuildingStep'].split('_')[1]

        # df['Bouwlaag promat'] = df['BuildingStep'].str.split('_').str[1]
    # Drop the BuildingStep column
    df.drop('BuildingStep', axis=1, inplace=True)
    bouwlaag_dict = helpers.bouwlaag_translation()
    df['Bouwlaag promat'] = df['Bouwlaag promat'].replace(bouwlaag_dict)

    df["Order"] = ordernummer
    df["Dikte"] = df["Dikte"].astype(int)
    df["Materiaal"] = df["Materiaal"] + " " + df["Dikte"].astype(str)
    df = df[
        [
            "Order",
            "Modulenaam",
            "Station",
            "Productnaam",
            "Materiaal",
            "Productcode",
            "Lengte",
            "Breedte",
            "Dikte",
            "Aantal",
            "Bouwlaag promat",
            "Nesting Prioriteit",
        ]
    ]
    df = df.rename(columns={"Productnaam": "Naam"})

    df = df.astype({"Aantal": "int"})
    df = df.groupby(df.columns.tolist(), as_index=False, dropna=False).size()
    df["Aantal"] = (df["Aantal"] * df["size"]).astype(int)
    df = df.drop("size", axis=1)

    # Normaal-Normaal, bulk = False and casettes = False, BN
    if not bulk:
        df = df[~df["Productcode"].isin(bulk_file)]
        df.to_csv(f"{path}/{ordernummer}-{project}-{bouwnummer}-VMG.csv", index=False, sep=";")

    # Normaal-Bulk, bulk = True and casettes = False, BATCH
    elif bulk:
        df_bulk = df[df["Productcode"].isin(bulk_file)]
        if not df_bulk.empty:
            df_bulk.to_csv(f"{path}/{ordernummer}-{project}-VMG-BULK.csv", index=False, sep=";")


def ERP(df: pd.DataFrame, path: str) -> None:
    """Gets the ERP parts from the dataframe and saves it to a CSV file.

    Args:
        df (pd.DataFrame): The dataframe with all the parts.
        path (str): The path to save the CSV file.
    """
    project, bouwnummer = df["Projectnummer"].iloc[0], df["Bouwnummer"].iloc[0]

    df_unit = df[df["Eenheid"].isin(["unit", "Each"])]
    df_metric = df[~df["Eenheid"].isin(["unit", "Each"])]

    # Compression on units
    df_unit = df_unit.sort_values(by=["Productnaam", "Station", "Dikte", "Breedte", "Lengte"])
    df_unit = df_unit.groupby(
        ["Productcode", "Productnaam", "Moduletype", "Materiaal", "Station", "Eenheid"],
        as_index=False,
    ).agg(
        dict(
            map(
                (lambda x: (x, "first") if x != "Aantal" else (x, "sum")),
                df_unit.columns.tolist(),
            )
        )
    )

    # Compression on m1, m2
    df_metric = df_metric.sort_values(
        by=["Productnaam", "Station", "Dikte", "Breedte", "Lengte"]
    )
    df_metric = df_metric.groupby(
        ["Productcode", "Productnaam", "Moduletype", "Materiaal", "Station", "Eenheid"],
        as_index=False,
    ).agg(
        dict(
            map(
                (
                    lambda x: (x, "sum")
                    if x == "Aantal"
                    else ((x, "sum") if x == "Gewicht" else (x, "first"))
                ),
                df_metric.columns.tolist(),
            )
        )
    )

    df_merged = pd.concat([df_unit, df_metric], ignore_index=True)
    df_merged["Productnaam"] = df_merged["Productnaam"].astype("string")
    df_merged = df_merged.sort_values(by=["Productnaam", "Moduletype"])
    df_merged = df_merged.round({"Aantal": 2, "Gewicht": 3})
    df_merged = df_merged.rename(
        columns={
            "Categorie": "Artikelcategorie",
            "IFC bestand": "IFC-bestand",
        }
    )

    df_merged["IFC-bestand"] = df_merged["IFC-bestand"].str.replace(" ", "_")

    # Translate "Each" back to "unit" in the output
    df_merged["Eenheid"] = df_merged["Eenheid"].replace("Each", "unit")

    # Override Voorraad based on material type
    # Milling materials (LVLQ, LVLS, CEM, SPANO, PRO, MDF) = "Nee", others = "Ja"
    df_merged["Voorraad"] = df_merged["Materiaal"].apply(
        lambda mat: "Nee" if pd.notna(mat) and any(x in str(mat).upper() for x in ["LVLQ", "LVLS", "CEM", "SPANO", "PRO", "MDF"]) else "Ja"
    )

    if 'BuildingStep' in df.columns:
        # Remove the BuildingStep column
        df_merged.drop('BuildingStep', axis=1, inplace=True)

    df_merged.to_csv(f"{path}/{project}-{bouwnummer}-ERP.csv", index=False, sep=";")


def WS198(df: pd.DataFrame, path: str) -> None:
    project, bouwnummer = df["Projectnummer"].iloc[0], df["Bouwnummer"].iloc[0]

    # Get all products where "Station" is WS198
    df = df[df["Station"] == "WS198"]
    if df.empty:
        return

    df_unit = df[df["Eenheid"].isin(["unit", "Each"])]
    df_metric = df[~df["Eenheid"].isin(["unit", "Each"])]

    # Compression on units
    df_unit = df_unit.sort_values(by=["Productnaam", "Station", "Dikte", "Breedte", "Lengte"])
    df_unit = df_unit.groupby(
        ["Productcode", "Productnaam", "Moduletype", "Materiaal", "Station", "Eenheid"],
        as_index=False,
    ).agg(
        dict(
            map(
                (lambda x: (x, "first") if x != "Aantal" else (x, "sum")),
                df_unit.columns.tolist(),
            )
        )
    )

    # Compression on m1, m2
    df_metric = df_metric.sort_values(
        by=["Productnaam", "Station", "Dikte", "Breedte", "Lengte"]
    )
    df_metric = df_metric.groupby(
        ["Productcode", "Productnaam", "Moduletype", "Materiaal", "Station", "Eenheid"],
        as_index=False,
    ).agg(
        dict(
            map(
                (
                    lambda x: (x, "sum")
                    if x == "Aantal"
                    else ((x, "sum") if x == "Gewicht" else (x, "first"))
                ),
                df_metric.columns.tolist(),
            )
        )
    )

    df_merged = pd.concat([df_unit, df_metric], ignore_index=True)
    df_merged["Productnaam"] = df_merged["Productnaam"].astype("string")
    df_merged = df_merged.sort_values(by=["Productcode"])
    df_merged = df_merged.round({"Aantal": 2})

    df_ws198 = df_merged[
        [
            "Productnaam",
            "Productcode",
            "Aantal",
            "Eenheid",
            "Modulenaam",
            "Breedte",
            "Lengte",
            "Dikte",
        ]
    ]

    # Translate "Each" back to "unit" in the output
    df_ws198["Eenheid"] = df_ws198["Eenheid"].replace("Each", "unit")

    df_ws198.to_csv(f"{path}/{project}-{bouwnummer}-WS198.csv", index=False, sep=";")
    

def Houtlijst(df: pd.DataFrame, path: str) -> None:
    """Gets the Van Hulst & Boerboom parts from the dataframe and saves it to a CSV file. Use the same file structure as ERP.

    Args:
        df (pd.DataFrame): The dataframe with all the parts.
        path (str): The path to save the CSV file.
    """
    project = df["Projectnummer"].iloc[0]

    # Filter for products that go to Boerboom & Van Hulst (exclude PRO/FERM materials)
    df = df[~df["Materiaal"].str.contains("PRO|FERM", na=False)]

    if df.empty:
        return

    # Filter for materials that go to milling companies
    df = df[df["Materiaal"].str.contains("LVLQ|LVLS|CEM|SPANO|PRO|MDF", case=False, na=False)]

    if df.empty:
        return

    # Determine Leverancier (BB or VH) based on product characteristics
    # BB criteria: LVLQ 90/100/144/69, LVLS 45 (>3360mm), SPANO 18 (>2700mm), or BAUB material
    bb_mask = (
        df["Productnaam"].str.contains("LVLQ 90|LVLQ 100|LVLQ 144|LVLQ 69") |
        ((df["Productnaam"].str.contains("LVLS 45")) & (df["Lengte"] > 3360)) |
        ((df["Productnaam"].str.contains("SPANO 18")) & (df["Lengte"] > 2700)) |
        df["Materiaal"].str.contains("BAUB")
    )
    df["Leverancier"] = np.where(bb_mask, "BB", "VH")

    df_unit = df[df["Eenheid"].isin(["unit", "Each"])]
    df_metric = df[~df["Eenheid"].isin(["unit", "Each"])]

    # Compression on units
    df_unit = df_unit.sort_values(by=["Productnaam", "Station", "Dikte", "Breedte", "Lengte"])
    df_unit = df_unit.groupby(
        ["Productcode", "Productnaam", "Moduletype", "Materiaal", "Station", "Eenheid"],
        as_index=False,
    ).agg(
        dict(
            map(
                (lambda x: (x, "first") if x != "Aantal" else (x, "sum")),
                df_unit.columns.tolist(),
            )
        )
    )

    # Compression on m1, m2
    df_metric = df_metric.sort_values(
        by=["Productnaam", "Station", "Dikte", "Breedte", "Lengte"]
    )
    df_metric = df_metric.groupby(
        ["Productcode", "Productnaam", "Moduletype", "Materiaal", "Station", "Eenheid"],
        as_index=False,
    ).agg(
        dict(
            map(
                (
                    lambda x: (x, "sum")
                    if x == "Aantal"
                    else ((x, "sum") if x == "Gewicht" else (x, "first"))
                ),
                df_metric.columns.tolist(),
            )
        )
    )

    df_merged = pd.concat([df_unit, df_metric], ignore_index=True)
    df_merged["Productnaam"] = df_merged["Productnaam"].astype("string")
    df_merged = df_merged.sort_values(by=["Productnaam", "Moduletype"])
    df_merged = df_merged.round({"Aantal": 2, "Gewicht": 3})
    df_merged = df_merged.rename(
        columns={
            "Categorie": "Artikelcategorie",
            "IFC bestand": "IFC-bestand",
        }
    )

    df_merged["IFC-bestand"] = df_merged["IFC-bestand"].str.replace(" ", "_")

    # Translate "Each" back to "unit" in the output
    df_merged["Eenheid"] = df_merged["Eenheid"].replace("Each", "unit")

    if 'BuildingStep' in df_merged.columns:
        # Remove the BuildingStep column
        df_merged.drop('BuildingStep', axis=1, inplace=True)

    df_merged.to_csv(f"{path}/{project}-HOUTLIJST.csv", index=False, sep=";")