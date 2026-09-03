from globals import SEED, RANDOMIZED_SEED, FOX_RUN_DRAFT_ORDER, SMITHFIELD_DRAFT_ORDER
from manager import launch_agent_ui

import pandas as pd
import random                              
from scipy.stats import norm


# TODO: rewrite to integrate new infrastructure
# Random pick analysis functions
def run_player_counts_by_round_in_simulation():
    n_full_draft_simulations = 25
    player_counts_by_round = {}

    for league in ['Fox Run', 'Smithfield']:

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
    df.to_csv('analysis_results/player_ct_by_round.csv')

def run_player_selection_by_pick():
    n_full_draft_simulations = 25
    user = 'Alex'
    
    for league, prefix, order in zip(['Fox Run', 'Smithfield'], ['fr', 'sm'], [FOX_RUN_DRAFT_ORDER, SMITHFIELD_DRAFT_ORDER]):
        if league == 'Fox Run':
            # Skip for now
            continue

        all_sim_data = []
        players_picked = {}

        for sim_num in range(n_full_draft_simulations):
            print(f'Simulation number {sim_num + 1}')
            players_drafted_in_order = run_draft_type(league, 'all random', simulation=True, print_results=False, print_picks=True, use_agent=True, user='Alex')
            print('Storing...\n\n')

            players_picked[f'sim{sim_num}'] = []
            
            # Enumerate to capture the exact pick number (1-indexed)
            for pick_idx, player in enumerate(players_drafted_in_order, start=1):
                all_sim_data.append({
                    'Player': player.name,
                    'Pick': pick_idx
                })

                players_picked[f'sim{sim_num}'].append(player.name)


        # Create DataFrame from all captured picks across all simulations
        df_all_picks = pd.DataFrame(all_sim_data)
        df_players_picked = pd.DataFrame(players_picked)

        # Save the structured data to CSV
        df_players_picked.to_csv(f'sim_drafted_players_{prefix}.csv', index=False)

        df_avg_picks = (
            df_all_picks.groupby('Player')['Pick']
            .agg(Avg_Pick='mean', Std_Dev_Pick='std', Ct_Picks='count')
            .reset_index()
            .fillna(1) 
            .sort_values(by='Avg_Pick')
        )

        # Use count to fill in missing picks with undrafted pick 193
        df_avg_picks.loc[df_avg_picks['Ct_Picks'] < n_full_draft_simulations, 'Avg_Pick'] = ((df_avg_picks['Avg_Pick'] * df_avg_picks['Ct_Picks']) + 193 * (n_full_draft_simulations - df_avg_picks['Ct_Picks'])) / n_full_draft_simulations

        my_pick_odd = order.index(user) + 1
        my_pick_even = 13 - my_pick_odd 

        df_avg_picks['Std_Dev_Pick'] = df_avg_picks['Std_Dev_Pick'].clip(lower=0.1)
        
        for rd in range(16):
            if rd % 2 == 1:
                my_pick = my_pick_even
            else:
                my_pick = my_pick_odd

            df_avg_picks[f'B_RD{rd}'] = norm.cdf(my_pick + (rd * 12), loc=df_avg_picks['Avg_Pick'], scale=df_avg_picks['Std_Dev_Pick'])
        
        # Save the structured average data to CSV
        df_avg_picks.to_csv(f'analysis_results/sim_drafted_avg_{prefix}.csv', index=False)

def run_sims_for_options_by_pick():
    n_full_draft_simulations = 25
    user = 'Alex'
    
    for league, prefix in zip(['Fox Run', 'Smithfield'], ['fr', 'sm']):
        if league == 'Smithfield':
            continue

        overall_results = {}

        for sim_num in range(n_full_draft_simulations):
            print(f'Simulation number {sim_num + 1}')
            relevant_dict = run_draft_type(league, 'all random', simulation=True, print_results=False, print_picks=True, use_agent=False, user=user, output_type='next_up_each_round')
            print('Storing...\n\n')

            for player_name, info in relevant_dict.items():
                for round, ct in info.items():
                    if player_name not in overall_results.keys():
                        overall_results[player_name] = {}
                    if round not in overall_results[player_name].keys():
                        overall_results[player_name][round] = 0
                    overall_results[player_name][round] += ct
                    

        df = pd.DataFrame.from_dict(overall_results, orient='index')
        df.to_csv(f'analysis_results/next_up_by_round_{prefix}.csv')
    print('Done.')



if __name__ == '__main__':
    random.seed(RANDOMIZED_SEED)

    league = 'Fox Run'
    user = 'Alex'
    draft_type = 'mock draft'
    simulation = True
    use_interface = (draft_type != 'all random')


    if use_interface:
        launch_agent_ui(league=league, user=user, draft_type=draft_type, simulation=simulation)