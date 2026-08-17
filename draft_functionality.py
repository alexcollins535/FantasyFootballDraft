from infrastructure import DraftBlackboard, Player
from preprocessing import get_player_data_dict
from globals import N_SIMULATIONS, N_WORKERS

import random
from concurrent.futures import ProcessPoolExecutor, as_completed


GLOBAL_SIM_ID = 0

def initialize_draft(league: str, type: str) -> DraftBlackboard:
    print('Initializing draft.\n')
    player_data_dict = get_player_data_dict()

    user_selection = type != 'all random'   # The only case this should be false is in the all random draft
    draft_blackboard = DraftBlackboard(league, user_selection=user_selection)

    keeper_list = []
    if draft_blackboard.keepers is not None:
        for k, v in draft_blackboard.keepers.items():
            keeper_list.append(v['NAME'])
            draft_blackboard.keepers[k]['PLAYER_OBJ'] = Player(v['NAME'], player_data_dict[v['NAME']])

    for name, data in player_data_dict.items():
        if name in keeper_list or 'OVR RK' not in data.keys():
            continue

        player = Player(name, data)
        draft_blackboard.next_up_queue.push(player)

    # Initialize the queue odds and sort
    draft_blackboard.update_odds()
    return draft_blackboard


def pad_string(string: str, num_characters_total: int) -> str:
    return string + (' ' * (num_characters_total - len(string)))


def run_one_simulation(sim_id:int, n_picks: int, draft_blackboard: DraftBlackboard) -> list[Player]:
    random.seed(sim_id)
    for _ in range(n_picks):
        draft_blackboard.make_random_pick(print_picks=False)
    picked_players = draft_blackboard.players_drafted_by_owner['LEAGUE'][(-1 * n_picks):]
    return picked_players


def merge_result(picked_players, sim_player_counts, draft_blackboard):
    # Add the picked players to counts
    for player in picked_players:
        if player.name in sim_player_counts.keys():
            sim_player_counts[player.name]['count'] += 1
        else:
            # Add player info to tracker
            sim_player_counts[player.name] = {'count': 1}
            sim_player_counts[player.name]['POS'] = player.pos
            sim_player_counts[player.name]['TEAM'] = player.team
            sim_player_counts[player.name]['OVR_RK'] = player.ovr_rk

            if player.name in draft_blackboard.additional_data_dict.keys():
                sim_player_counts = add_player_info(sim_player_counts, player, draft_blackboard)

    return sim_player_counts


def run_all_simulations(sim_player_counts: dict, picks_before_next: int, draft_blackboard: DraftBlackboard):
    global GLOBAL_SIM_ID

    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        # Submit all jobs, pool queues them internally
        futures = {
            executor.submit(run_one_simulation, sim_id, picks_before_next, draft_blackboard): sim_id for sim_id in range(GLOBAL_SIM_ID, GLOBAL_SIM_ID + N_SIMULATIONS)
        }

        GLOBAL_SIM_ID += N_SIMULATIONS

        # as_completed yields each future when its worker finishes
        for future in as_completed(futures):
            sim_id = futures[future]
            try:
                picked_players = future.result()
                sim_player_counts = merge_result(picked_players, sim_player_counts, draft_blackboard)
            except Exception as e:
                print(f'Sim {sim_id} failed: {e}')

    return sim_player_counts
    

def run_simulation(draft_blackboard: DraftBlackboard) -> dict[str, dict]:
    ''' Simulate all picks before the next n_simulations times '''
    if draft_blackboard.current_pick_in_round == 12:
        picks_before_next = 23
    else:
        picks_before_next = (12 - draft_blackboard.current_pick_in_round) * 2 + 1

    sim_player_counts = {}
    # Add info for the next 100 players
    for player in draft_blackboard.next_up_queue.heap[:100]:
        sim_player_counts[player.name] = {'count': 0}
        sim_player_counts[player.name]['POS'] = player.pos
        sim_player_counts[player.name]['TEAM'] = player.team
        sim_player_counts[player.name]['OVR_RK'] = player.ovr_rk

        if player.name in draft_blackboard.additional_data_dict.keys():
            sim_player_counts = add_player_info(sim_player_counts, player, draft_blackboard)

    sim_player_counts = run_all_simulations(sim_player_counts, picks_before_next, draft_blackboard)    

    # Sort by overall rank
    sim_player_counts = {k: v for k, v in sorted(sim_player_counts.items(), key=lambda item: item[1]['OVR_RK'])}
    return sim_player_counts


def add_player_info(dict, player: Player, draft_blackboard: DraftBlackboard) -> dict:
    dict[player.name]['PROJ_AVG'] = draft_blackboard.additional_data_dict[player.name]['ProjAvg']
    dict[player.name]['L_OUT'] = draft_blackboard.additional_data_dict[player.name]['OutLast']
    dict[player.name]['L_ISHELP'] = draft_blackboard.additional_data_dict[player.name]['IsHelp']
    dict[player.name]['L_NHELP'] = draft_blackboard.additional_data_dict[player.name]['NeedHelp']
    dict[player.name]['OL_TIER'] = draft_blackboard.additional_data_dict[player.name]['OLTier']
    dict[player.name]['INJ_RISK'] = draft_blackboard.additional_data_dict[player.name]['InjRisk']
    dict[player.name]['PRJ_OUT'] = draft_blackboard.additional_data_dict[player.name]['ProjOut']
    dict[player.name]['PRJ_PPR'] = draft_blackboard.additional_data_dict[player.name]['ProjPPR']
    return dict


def print_next_up_players(draft_blackboard: DraftBlackboard, simulation: bool=False) -> None:

    if simulation: 
        next_up_dict = run_simulation(draft_blackboard)
    else:
        # Generate something next_up_dict-like by pulling from queue.
        next_up_dict = {}
        for player in draft_blackboard.next_up_queue.heap[:12]:
            next_up_dict[player.name] = {'POS': player.pos}
            next_up_dict[player.name]['TEAM'] = player.team
            next_up_dict[player.name]['OVR_RK'] = player.ovr_rk

            if player.name in draft_blackboard.additional_data_dict.keys():
                next_up_dict[player.name]['PROJ_AVG'] = draft_blackboard.additional_data_dict[player.name]['ProjAvg']
                next_up_dict[player.name]['L_OUT'] = draft_blackboard.additional_data_dict[player.name]['OutLast']
                next_up_dict[player.name]['L_ISHELP'] = draft_blackboard.additional_data_dict[player.name]['IsHelp']
                next_up_dict[player.name]['L_NHELP'] = draft_blackboard.additional_data_dict[player.name]['NeedHelp']
                next_up_dict[player.name]['OL_TIER'] = draft_blackboard.additional_data_dict[player.name]['OLTier']
                next_up_dict[player.name]['INJ_RISK'] = draft_blackboard.additional_data_dict[player.name]['InjRisk']
                next_up_dict[player.name]['PRJ_OUT'] = draft_blackboard.additional_data_dict[player.name]['ProjOut']
                next_up_dict[player.name]['PRJ_PPR'] = draft_blackboard.additional_data_dict[player.name]['ProjPPR']
                                    

    print_in_terminal(next_up_dict, simulation)


def print_in_terminal(next_up_dict: dict[str, dict], simulation: bool) -> None:
    if simulation:
        header = ['NAME', 'OVR_RK', 'B_NEXT', 'POS', 'TEAM', 'PROJ_AVG', 'L_ISHELP', 'L_NHELP', 'L_OUT', 'OL_TIER', 'INJ_RISK', 'PRJ_OUT', 'PRJ_PPR']
    else:
        header = ['NAME', 'OVR_RK', 'POS', 'TEAM', 'PROJ_AVG', 'L_ISHELP', 'L_NHELP', 'L_OUT', 'OL_TIER', 'INJ_RISK', 'PRJ_OUT', 'PRJ_PPR']
    
    char_per = 9
    char_name = 25

    print('\nNext best players:')
    header_string = ''
    for string in header:
        if string == 'NAME':
            header_string += pad_string(string, char_name)
        else:
            header_string += pad_string(string, char_per)
    print(header_string)
        
    for player_name, info in next_up_dict.items():
        print_string = ''
        for item in header:
            if item == 'B_NEXT':
                value = info['count'] / N_SIMULATIONS
            elif item == 'NAME':
                value = player_name
            elif item not in info.keys():
                value = 'N/A'
            else:
                value = info[item]

            if isinstance(value, float):
                if item in ['L_ISHELP', 'L_NHELP', 'B_NEXT']:
                    value = str(round(value * 100, 1)) + '%'
                else:
                    value = str(round(value, 1))

            print_string += pad_string(str(value), char_name if item == 'NAME' else char_per)

        print(print_string)


def run_draft_type(league: str, type: str, user: str=None, simulation: bool=True, print_results: bool=True, print_picks: bool=True) -> list[Player]:
    '''
    Returns a list of the players drafted, in the order drafted.
    '''
    assert type in ('all random', 'all select', 'mock draft')
    draft_blackboard = initialize_draft(league, type)
    keeper_drafted = False
    while draft_blackboard.in_progress:
        if draft_blackboard.keepers is not None:
            if draft_blackboard.keepers[draft_blackboard.current_pick_owner]['ROUND'] == draft_blackboard.current_round:
                # Pull the player object from the keepers dictionary and make the pick
                draft_blackboard.draft_player(draft_blackboard.keepers[draft_blackboard.current_pick_owner]['PLAYER_OBJ'], print_picks=print_picks, keeper_pick=True)
                keeper_drafted = True
            else:
                keeper_drafted = False

        if not keeper_drafted:
            if type == 'all random':
                draft_blackboard.make_random_pick(print_picks=print_picks)

            elif type == 'all select':
                draft_blackboard.make_select_pick(draft_type=type)

            elif type == 'mock draft':
                if draft_blackboard.current_pick_owner == user:
                    if draft_blackboard.current_round != draft_blackboard.last_round:
                        print_next_up_players(draft_blackboard, simulation=simulation)

                    draft_blackboard.make_select_pick(draft_type=type)
                else:
                    draft_blackboard.make_random_pick(print_picks=print_picks)

    if print_results:
        draft_blackboard.print_results()

    return draft_blackboard.players_drafted_by_owner['LEAGUE']
