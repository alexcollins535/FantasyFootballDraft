from globals import SEED, RANDOMIZED_SEED
from draft_functionality import run_draft_type
from user_interface import launch_ui

import pandas as pd
import random


def run_player_counts_by_round_in_simulation():
    n_full_draft_simulations = 25
    player_counts_by_round = {}

    for league in ('Fox Run', 'Smithfield'):

        for sim_num in range(n_full_draft_simulations):
            print(f'Simulation number {sim_num + 1}')
            players_drafted_in_order = run_draft_type(league, 'all random', simulation=True, print_results=False, print_picks=False)
            print('Storing...\n\n')
            rd = 1
            pick_in_rd = 1
            for player in players_drafted_in_order:
    
                if player.name not in player_counts_by_round.keys():
                    player_counts_by_round[player.name] = {f'Smithfield 1': 0}
                    player_counts_by_round[player.name][f'Fox Run 1'] = 0
                    for i in range(1, 16):
                        for league1 in ('Fox Run', 'Smithfield'):
                            player_counts_by_round[player.name][f'{league1} {i+1}'] = 0
                        
                player_counts_by_round[player.name][f'{league} {rd}'] += 1

                if pick_in_rd == 12:
                    pick_in_rd = 1
                    rd += 1
                else:
                    pick_in_rd += 1

    df = pd.DataFrame.from_dict(player_counts_by_round, orient='index')
    df.to_csv('player_ct_by_round.csv')


def run_player_selection_by_pick():
    n_full_draft_simulations = 25
    
    for league, prefix in zip(['Fox Run', 'Smithfield'], ['fr', 'sm']):
        player_lists = []

        for sim_num in range(n_full_draft_simulations):
            print(f'Simulation number {sim_num + 1}')
            players_drafted_in_order = run_draft_type(league, 'all random', simulation=True, print_results=False, print_picks=False)
            print('Storing...\n\n')
            player_names = [x.name for x in players_drafted_in_order]

            player_lists.append(player_names)

        transposed = list(map(list, zip(*player_lists)))
        column_names = [f'Sim {x}' for x in range(n_full_draft_simulations)]
        df = pd.DataFrame(transposed, columns=column_names)
        df.to_csv(f'sim_drafted_{prefix}.csv')

    

if __name__ == '__main__':
    random.seed(SEED)

    run_player_selection_by_pick()

    # use_interface = True

    # league = 'Fox Run'
    # user = 'Alex'
    # draft_type = 'mock draft'
    # simulation = True

    # if use_interface:
    #     launch_ui(league=league, user=user, draft_type=draft_type, simulation=simulation)
    # else:
    #     run_draft_type(league=league, user=user, draft_type=draft_type, simulation=simulation)