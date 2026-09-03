from infrastructure import DraftBlackboard, Player, DraftState, DraftEngine
from preprocessing import get_player_data_dict
from globals import N_SIMULATIONS, N_WORKERS
from agents import LogicalDraftAgent

import random
from concurrent.futures import ProcessPoolExecutor, as_completed


GLOBAL_SIM_ID = 0

def run_one_simulation(sim_id:int, n_picks: int, state: DraftState, blackboard: DraftBlackboard) -> list[Player]:
    import copy
    random.seed(sim_id)
    # Deep copy the mutable parts of state for this worker
    local_state = {
        **state,
        'next_up_queue': copy.deepcopy(state['next_up_queue']),
        'pos_counts_by_owner': copy.deepcopy(state['pos_counts_by_owner']),
        'pos_counts_this_round': dict(state['pos_counts_this_round']),
        'players_drafted_by_owner': {
            o: list(names) for o, names in state['players_drafted_by_owner'].items()
        },
    }
    
    engine = DraftEngine(blackboard)
    for _ in range(n_picks):
        odds_update = engine.update_odds(local_state)
        local_state = {**local_state, **odds_update}
        pick_update = engine.make_random_pick(local_state)
        local_state = {**local_state, **pick_update}

    return local_state['players_drafted_by_owner']['LEAGUE'][(-1 * n_picks):]


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

            if hasattr(draft_blackboard, 'additional_data_dict') and player.name in draft_blackboard.additional_data_dict.keys():
                sim_player_counts = add_player_info(sim_player_counts, player, draft_blackboard)

    return sim_player_counts


def run_all_simulations(sim_player_counts: dict, picks_before_next: int, state: DraftState, blackboard: DraftBlackboard):
    global GLOBAL_SIM_ID

    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        # Submit all jobs, pool queues them internally
        futures = {
            executor.submit(run_one_simulation, sim_id, picks_before_next, state, blackboard): sim_id 
            for sim_id in range(GLOBAL_SIM_ID, GLOBAL_SIM_ID + N_SIMULATIONS)
        }

        GLOBAL_SIM_ID += N_SIMULATIONS

        # as_completed yields each future when its worker finishes
        for future in as_completed(futures):
            sim_id = futures[future]
            try:
                picked_players = future.result()
                sim_player_counts = merge_result(picked_players, sim_player_counts, blackboard)
            except Exception as e:
                print(f'Sim {sim_id} failed: {e}')

    # # Uncomment for single thread
    # for sim_id in range(GLOBAL_SIM_ID, GLOBAL_SIM_ID + N_SIMULATIONS):
    #     picked_players = run_one_simulation(sim_id, picks_before_next, draft_blackboard)
    #     sim_player_counts = merge_result(picked_players, sim_player_counts, draft_blackboard)
    
    # GLOBAL_SIM_ID += N_SIMULATIONS

    return sim_player_counts
    

def run_simulation(draft_blackboard: DraftBlackboard) -> dict[str, dict]:
    ''' Simulate all picks before the next n_simulations times '''
    # TODO: not currently in use, update with new infrastructure
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

        if hasattr(draft_blackboard, 'additional_data_dict') and player.name in draft_blackboard.additional_data_dict.keys():
            sim_player_counts = add_player_info(sim_player_counts, player, draft_blackboard)

    sim_player_counts = run_all_simulations(sim_player_counts, picks_before_next, draft_blackboard)    

    # Sort by overall rank
    sim_player_counts = {k: v for k, v in sorted(sim_player_counts.items(), key=lambda item: item[1]['OVR_RK'])}
    return sim_player_counts


def add_player_info(dict, player: Player, draft_blackboard: DraftBlackboard) -> dict:
    dict[player.name]['PROJ_AVG'] = draft_blackboard.additional_data_dict[player.name].get('ProjAvg')
    dict[player.name]['L_OUT'] = draft_blackboard.additional_data_dict[player.name].get('OutLast')
    dict[player.name]['L_ISHELP'] = draft_blackboard.additional_data_dict[player.name].get('IsHelp')
    dict[player.name]['L_NHELP'] = draft_blackboard.additional_data_dict[player.name].get('NeedHelp')
    dict[player.name]['OL_TIER'] = draft_blackboard.additional_data_dict[player.name].get('OLTier')
    dict[player.name]['INJ_RISK'] = draft_blackboard.additional_data_dict[player.name].get('InjRisk')
    dict[player.name]['PRJ_OUT'] = draft_blackboard.additional_data_dict[player.name].get('ProjOut')
    dict[player.name]['PRJ_PPR'] = draft_blackboard.additional_data_dict[player.name].get('ProjPPR')
    dict[player.name]['INJURY'] = draft_blackboard.additional_data_dict[player.name].get('Injury')
    return dict


