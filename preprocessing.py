import pandas as pd
import numpy as np
import json
from globals import (REF_FILEPATH, POS_RK_SHEET, OVR_RK_SHEET, PAST_DRAFT_SHEET, DRAFT_BY_TEAM_SHEET, ADDITIONAL_DATA_JSON, ADDITIONAL_DATA_SHEET, POS_LIST, 
                     PLAYER_DATA_JSON, DRAFT_DATA_JSON, LEAGUES, STD_DEFAULT)

def generate_player_data_json():
    overall_rank_raw = pd.read_excel(REF_FILEPATH, sheet_name=OVR_RK_SHEET)
    position_rank_raw = pd.read_excel(REF_FILEPATH, sheet_name=POS_RK_SHEET)
    player_data_dict = {}

    # Process positional rankings
    col_name_ref = {
        'QB': {
            'RK': 'RK', 'NAME': 'PLAYER NAME', 'BEST': 'BEST', 'WORST': 'WORST', 'AVG': 'AVG.', 'STDEV': 'STD.DEV', 'ECR VS. ADP': 'ECR VS. ADP'
        },
        'RB': {
            'RK': 'RK.1', 'NAME': 'PLAYER NAME.1', 'BEST': 'BEST.1', 'WORST': 'WORST.1', 'AVG': 'AVG..1', 'STDEV': 'STD.DEV.1', 'ECR VS. ADP': 'ECR VS. ADP.1'
        },
        'WR': {
            'RK': 'RK.2', 'NAME': 'PLAYER NAME.2', 'BEST': 'BEST.2', 'WORST': 'WORST.2', 'AVG': 'AVG..2', 'STDEV': 'STD.DEV.2', 'ECR VS. ADP': 'ECR VS. ADP.2'
        },
        'TE': {
            'RK': 'RK.3', 'NAME': 'PLAYER NAME.3', 'BEST': 'BEST.3', 'WORST': 'WORST.3', 'AVG': 'AVG..3', 'STDEV': 'STD.DEV.3', 'ECR VS. ADP': 'ECR VS. ADP.3'
        },
        'PK': {
            'RK': 'RK.4', 'NAME': 'PLAYER NAME.4', 'BEST': 'BEST.4', 'WORST': 'WORST.4', 'AVG': 'AVG..4', 'STDEV': 'STD.DEV.4', 'ECR VS. ADP': 'ECR VS. ADP.4'
        },
        'DEF': {
            'RK': 'RK.5', 'NAME': 'PLAYER NAME.5', 'BEST': 'BEST.5', 'WORST': 'WORST.5', 'AVG': 'AVG..5', 'STDEV': 'STD.DEV.5', 'ECR VS. ADP': 'ECR VS. ADP.5'
        }
    }
    for _, row in position_rank_raw.iterrows():

        for pos in POS_LIST:
            # Check if valid 
            name_string = row[col_name_ref[pos]['NAME']]
            if name_string != name_string:
                continue
            parts = name_string.strip().split()
            team = parts[-1].replace('(', '').replace(')', '')
            name = ' '.join(parts[:-1])

            rk = int(row[col_name_ref[pos]['RK']])
            best = int(row[col_name_ref[pos]['BEST']])
            worst = int(row[col_name_ref[pos]['WORST']])
            avg = float(row[col_name_ref[pos]['AVG']])
            stdev = float(row[col_name_ref[pos]['STDEV']])

            # print(name)
            # print(row)
            ecr_vs_adp = row[col_name_ref[pos]['ECR VS. ADP']]
            if pd.isna(ecr_vs_adp) or ecr_vs_adp == '-':
                adp = rk
            else:
                adp = rk + int(ecr_vs_adp)

            player_data_dict[name] = {
                'POS': pos, 'TEAM': team, 'POS RK': rk, 'POS BEST': best, 'POS WORST': worst, 'POS AVG': avg, 'POS STDEV': stdev, 'POS ADP': adp
            }

    # Process overall rankings
    for _, row in overall_rank_raw.iterrows():

        # Check if valid 
        name_string = row['PLAYER NAME'] 
        if name_string != name_string:
            continue
        parts = name_string.strip().split()
        name = ' '.join(parts[:-1])

        rk = int(row['RK'])
        best = int(row['BEST'])
        worst = int(row['WORST'])
        avg = float(row['AVG.'])
        stdev = float(row['STD.DEV'])

        ecr_vs_adp = row['ECR VS. ADP']
        if pd.isna(ecr_vs_adp) or ecr_vs_adp == '-':
            adp = rk
        else:
            adp = rk + int(ecr_vs_adp)


        if name not in player_data_dict:
            pos = row['POS']
            team = parts[-1].replace('(', '').replace(')', '')
            player_data_dict[name] = {'POS': pos, 'TEAM': team}

        player_data_dict[name]['OVR RK'] = rk
        player_data_dict[name]['OVR BEST'] = best
        player_data_dict[name]['OVR WORST'] = worst
        player_data_dict[name]['OVR AVG'] = avg
        player_data_dict[name]['OVR STDEV'] = stdev
        player_data_dict[name]['OVR ADP'] = adp

    with open(PLAYER_DATA_JSON, 'w') as f1:
        json.dump(player_data_dict, fp=f1)    
    
def generate_draft_data_json():        
    past_draft_raw = pd.read_excel(REF_FILEPATH, sheet_name=PAST_DRAFT_SHEET)
    draft_py_pos_raw = pd.read_excel(REF_FILEPATH, sheet_name=DRAFT_BY_TEAM_SHEET)
    draft_data_dict = {}
    
    # Process past draft data
    tracker = {}

    columns = past_draft_raw.columns
    league_starts = {}

    for league in LEAGUES:
        tracker[league] = {'QB': {}, 'RB': {}, 'WR': {}, 'TE': {}, 'DEF': {}, 'PK': {}}
        league_starts[league] = columns.get_loc(league) + 1

    for row in past_draft_raw.itertuples():
        for league in LEAGUES:
            if 'Round' in str(row[league_starts[league]]):
                for i, pos in enumerate(POS_LIST):
                    count = row[league_starts[league] + i + 1]
                    if count != count:
                        count = 0
                    else:
                        count = int(count)

                    if row[league_starts[league]] not in tracker[league][pos].keys():
                        tracker[league][pos][row[league_starts[league]]] = []

                    tracker[league][pos][row[league_starts[league]]].append(count)


    # Compute averages and stdevs
    for league in LEAGUES:
        draft_data_dict[league] = {'LEAGUE': {'AVG': {pos: {rd: np.mean(ct_list) for rd, ct_list in track_by_round.items()} 
                                                    for pos, track_by_round in tracker[league].items()}}}
        # Introduce the STD_DEFAULT in the case of a single draft for which we are calculating std
        draft_data_dict[league]['LEAGUE']['STDEV'] = {pos: {rd: np.std(ct_list) if len(ct_list) > 1 else STD_DEFAULT for rd, ct_list in track_by_round.items()} 
                                                    for pos, track_by_round in tracker[league].items()}
        
    # Process past pos counts by team
    columns = draft_py_pos_raw.columns
    col_names_by_league = {}
    key = None
    for column in columns:
        if column in LEAGUES:
            key = column
            col_names_by_league[key] = []
        elif key is not None and not('Unnamed' in column):
            col_names_by_league[key].append(column)

    for _, row in draft_py_pos_raw.iterrows():
        for league in LEAGUES:
            if 'OWNER_TOTALS' not in draft_data_dict[league].keys():
                draft_data_dict[league]['OWNER_TOTALS'] = {}

            col_names = col_names_by_league[league]
            owner = row[league]
            if pd.notna(owner): 
                draft_data_dict[league]['OWNER_TOTALS'][owner] = {
                        'QB': {'AVG': float(row[col_names[0]]), 'STD': float(row[col_names[1]])},
                        'RB': {'AVG': float(row[col_names[2]]), 'STD': float(row[col_names[3]])},
                        'WR': {'AVG': float(row[col_names[4]]), 'STD': float(row[col_names[5]])},
                        'TE': {'AVG': float(row[col_names[6]]), 'STD': float(row[col_names[7]])},
                        'DEF': {'AVG': float(row[col_names[8]]), 'STD': float(row[col_names[9]])},
                        'PK': {'AVG': float(row[col_names[10]]), 'STD': float(row[col_names[11]])},
                    }

    # Write the data dictionary to JSON
    with open(DRAFT_DATA_JSON, 'w') as f2:
        json.dump(draft_data_dict, fp=f2)

def generate_additional_data_json():
    additional_data_raw = pd.read_excel(REF_FILEPATH, sheet_name=ADDITIONAL_DATA_SHEET)

    additional_data_dict = {}
    for _, row in additional_data_raw.iterrows():
        additional_data_dict[row['PlayerName']] = {
            'ProjAvg': row['MyProjAvg'],
            'OutLast': row['OutLast'],
            'OLTier': row['OLTier'],
            'NeedHelp': row['NeedHelp'],
            'IsHelp': row['Helpx0.5'],
            'InjRisk': row['INJ Risk'],
            'ProjOut': row['ProjOut'],
            'ProjPPR': row['ProjPPR']
        }

    with open(ADDITIONAL_DATA_JSON, 'w') as f3:
        json.dump(additional_data_dict, fp=f3)


def get_player_data_dict():
    return get_data_dict(PLAYER_DATA_JSON)

def get_draft_data_dict():
    return get_data_dict(DRAFT_DATA_JSON)

def get_additional_data_dict():
    return get_data_dict(ADDITIONAL_DATA_JSON)

def get_data_dict(filepath):
    with open(filepath, 'r') as f:
        data_dict = json.load(f)
    return data_dict


if __name__ == '__main__':
    generate_player_data_json()
    generate_draft_data_json()
    generate_additional_data_json()
    print(f'Saved formatted data to {PLAYER_DATA_JSON}, {DRAFT_DATA_JSON}, {ADDITIONAL_DATA_JSON}')
        