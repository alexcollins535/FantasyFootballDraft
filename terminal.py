from infrastructure import DraftBlackboard, Player
from preprocessing import get_player_data_dict
from globals import N_SIMULATIONS
from agents import LogicalDraftAgent
from draft_functionality import run_simulation

import random
from globals import SEED


# Old terminal only workflow for debugging purposes.
# TODO: integrate with new infrastructure, will not run as is.


def initialize_draft(league: str, type: str, user_selection: bool=None) -> DraftBlackboard:
    print('Initializing draft.\n')
    player_data_dict = get_player_data_dict()

    if user_selection is None:
        user_selection = type != 'all random'   # The only case this should be false is in the all random draft
    draft_blackboard = DraftBlackboard(league, user_selection=user_selection)

    keeper_list = []
    if draft_blackboard.keepers is not None:
        for k, v in draft_blackboard.keepers.items():
            if v['NAME'] is not None and v['NAME'] != '':
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


def run_draft_type(league: str, type: str, user: str=None, simulation: bool=True, print_results: bool=True, print_picks: bool=True, use_agent: bool=False, output_type: str='drafted players') -> list[Player]:
    '''
    Returns a list of the players drafted, in the order drafted.
    '''
    assert type in ('all random', 'all select', 'mock draft')
    assert output_type in ('drafted_players', 'next_up_each_round')

    user_selection = (type != 'all random') | use_agent
    draft_blackboard = initialize_draft(league, type, user_selection=user_selection)
    if use_agent:
        draft_agent = LogicalDraftAgent()
    else:
        draft_agent = None

    if output_type == 'next_up_each_round':
        relevant_dict = {}

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
                if user == draft_blackboard.current_pick_owner:
                    if use_agent:
                        draft_blackboard.make_draft_agent_pick(print_picks=print_picks, draft_agent=draft_agent)
        
                    if output_type == 'next_up_each_round':
                        next_up_dict = run_simulation(draft_blackboard)
                        for player_name, info in next_up_dict.items():
                            if info['count'] / N_SIMULATIONS >= 0.40:
                                if player_name not in relevant_dict:
                                    relevant_dict[player_name] = {}
                                relevant_dict[player_name][draft_blackboard.current_round] = relevant_dict[player_name].get(draft_blackboard.current_round, 0) + 1
                    
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

    if output_type == 'drafted_players':
        return draft_blackboard.players_drafted_by_owner['LEAGUE']
    else:
        return relevant_dict




if __name__ == '__main__':
    random.seed(SEED)
    run_draft_type(league='Fox Run', type='mock draft', user='Alex', simulation=True)