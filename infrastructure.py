from preprocessing import get_player_data_dict, get_draft_data_dict, get_additional_data_dict
from globals import (POS_LIST, DRAFT_ROUNDS, STARTERS_BY_POSITION, FLEX_POSITIONS, NEED_STARTER, 
                     BACKUP_WHILE_NEED_STARTER, NEED_BACKUP, NO_NEED, 
                     MAX_BY_POS, LEAGUES, LEAGUE_TO_GLOBALS, C, K)

import random
import itertools
import math
import copy
import threading
import pickle

from scipy.stats import norm
from typing import TypedDict, Optional, Iterator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple


class Player:
    _id_generator = itertools.count(0)
    
    def __init__(self, name: str, player_data: dict):
        self.id = next(self._id_generator)
        self.name = name
        self.pos = player_data['POS']
        self.team = player_data['TEAM']

        # Rank average and stdev validation
        if 'OVR RK' in player_data.keys():
            if player_data['OVR RK'] < 500:
                self.ovr_rk = player_data['OVR RK']
                self.ovr_avg = player_data['OVR AVG']
                self.ovr_std = player_data['OVR STDEV'] if player_data['OVR STDEV'] > 0.001 else 0.001
                #self.ovr_adp = player_data['OVR ADP']
            else:
                self.ovr_rk = 500
                self.ovr_avg = 500
                self.ovr_std = 1
                #self.ovr_adp = 500
        else:
            self.ovr_rk = 500
            self.ovr_avg = 500
            self.ovr_std = 1
            #self.ovr_adp = 500

        if 'POS RK' in player_data.keys():
            if player_data['POS AVG'] < 200:
                self.pos_avg = player_data['POS AVG']
                self.pos_std = player_data['POS STDEV'] if player_data['POS STDEV'] > 0.001 else 0.001
                self.pos_adp = player_data['POS ADP']
            else:
                self.pos_avg = 200
                self.pos_std = 1
                self.pos_adp = 200

        else:
            self.pos_avg = 200
            self.pos_std = 1
            self.pos_adp = 200

        self.odds = 0.0


    def __lt__(self, other: 'Player') -> bool:
        # LESS THAN <=> BETTER THAN
        # Use OVR RK, only used in updating queue
        if self.ovr_rk != other.ovr_rk:
            return self.ovr_rk < other.ovr_rk
        else:
            return self.id < other.id


    def __eq__(self, other: object) -> bool:
        # EQUAL TO <=> SAME PLAYER
        return self.id == other.id


    def __hash__(self) -> int:
        return self.id


class NextUpQueue:
    def __init__(self):
        self.heap: list[Player] = []
        self.name_to_player_map: dict[str, Player] = {}


    def push(self, player: Player) -> None:
        self.heap.append(player)
        self._bubble_up(len(self.heap) - 1)
        self.name_to_player_map[player.name] = player


    def _bubble_up(self, index: int) -> None:
        while index > 0 and self.heap[index] < self.heap[index-1]:
            # Swap parent and child
            self.heap[index], self.heap[index-1] = self.heap[index-1], self.heap[index]
            index -= 1


    def pop(self, player_name: str) -> None:
        player = self.name_to_player_map.pop(player_name)
        self.heap.remove(player)


    def sort_queue(self) -> None:
        fully_sorted = False
        while not fully_sorted:
            # Re-sort until fully sorted
            fully_sorted = True
            for index in range(len(self.heap) - 1):
                # Sift down until better than next neighbor 
                if self.heap[index] > self.heap[index+1]:
                    # If worse, swap
                    self.heap[index], self.heap[index+1] = self.heap[index+1], self.heap[index]

                    if fully_sorted:
                        # Change was made, not fully sorted
                        fully_sorted = False


    def update_odds(self, odds_dict: dict[int, float]) -> None:
        for index in range(len(self.heap)):
            self.heap[index].odds = odds_dict[self.heap[index].id]


class DraftBlackboard:
    '''
    Static reference for draft session
    '''
    def __init__(self, league: str, user_selection: bool=False):
        assert league in LEAGUES

        order = LEAGUE_TO_GLOBALS[league]['ORDER']
        keepers = LEAGUE_TO_GLOBALS[league]['KEEPERS']

        if order is None:
            order = LEAGUE_TO_GLOBALS[league]['OWNERS'].copy()
            random.shuffle(order)

        self.player_data_dict = get_player_data_dict()
        if user_selection:
            self.additional_data_dict = get_additional_data_dict()

        draft_data = get_draft_data_dict()
        if league not in draft_data.keys():
            league = 'DEFAULT'

        self.draft_data_dict = draft_data[league]

        self.league = league
        self.order = order
        self.keepers = keepers
        self.final_round = DRAFT_ROUNDS



class DraftState(TypedDict):
    # Static
    draft_order: list[str]
    keepers: dict
    total_rounds: int
    user: str

    # Dynamic
    next_up_queue: NextUpQueue
    players_drafted_by_owner: dict[str, list] # LEAGUE: list[Player], others: list[str]    
    pos_counts_by_owner: dict[str, dict[str, int]]
    pos_counts_this_round: dict[str, int]
    last_round_pos_counts_this_round: Optional[dict[str, int]]
    current_round: int
    current_pick_in_round: int
    current_pick_overall: int
    current_pick_owner: str
    in_progress: bool
    action_log: list[str]
    pos_odds: dict[str, float]

    # Outputs
    simulation_results: Optional[dict]
    logical_pick: Optional[str]
    probabilistic_pick: Optional[str]
    gemini_pick: Optional[str]
    gemini_reasoning: Optional[str]

    # Human decision
    final_pick: Optional[str]   


class DraftEngine:
    '''
    Acts on DraftState
    '''
    def __init__(self, blackboard: DraftBlackboard):
        self.blackboard = blackboard

    def _calculate_odds(self, state: DraftState) -> tuple[dict[str, float], dict[int, float]]:
            blackboard = self.blackboard
            league_draft_data = blackboard.draft_data_dict
            owner = state['current_pick_owner']
            rd = state['current_round']
            league_pos_counts = state['pos_counts_by_owner']['LEAGUE']
            owner_pos_counts = state['pos_counts_by_owner'][owner]
            pos_counts_this_round = state['pos_counts_this_round']
            final_round = state['total_rounds']
            queue = state['next_up_queue']
            round_string = f'Round {rd}'
            
            # Evaluate if there are any positions missing for the current pick owner
            missing_pos = dict()
            max_pos = set()
            num_flex = 0
            for pos in POS_LIST:
                if STARTERS_BY_POSITION[pos] > owner_pos_counts[pos]:
                    missing_pos[pos] = STARTERS_BY_POSITION[pos] - owner_pos_counts[pos]
                else:
                    if MAX_BY_POS[pos] <= owner_pos_counts[pos]:
                        max_pos.add(pos)
    
                    if pos in FLEX_POSITIONS:
                        num_flex += owner_pos_counts[pos] - STARTERS_BY_POSITION[pos]
    
            if num_flex < STARTERS_BY_POSITION['FLEX']:
                missing_pos['FLEX'] = STARTERS_BY_POSITION['FLEX'] - num_flex
    
            count_missing = sum([v for v in missing_pos.values()])
    
            total_odds = 0
            raw_pos_odds = {}
            for pos in POS_LIST:
    
                # Position odds based on current team end position counts - current pick owner position counts, draft data dict end position counts
                scale1 = league_draft_data['OWNER_TOTALS'][owner][pos]['STD'] \
                        if isinstance(league_draft_data['OWNER_TOTALS'][owner][pos]['STD'], float) \
                        and league_draft_data['OWNER_TOTALS'][owner][pos]['STD'] > 0.001 else 0.001
                pos_odds_team_end_pos_counts = norm.sf(x=owner_pos_counts[pos] + 1,
                                                        loc=league_draft_data['OWNER_TOTALS'][owner][pos]['AVG'], 
                                                        scale=scale1)
    
                # Position odds based on need - current pick owner position counts
                if missing_pos:
                    if pos in missing_pos or ('FLEX' in missing_pos and pos in FLEX_POSITIONS):
                        pos_odds_team_need = NEED_STARTER
                    else:
                        if final_round - rd < count_missing:
                            # The late flag - the only picks that can be made are those that fill the open starter slots 
                            # The math: last round 16 - current round 14 = 3 picks left, the logic needs to be strictly less than count missing
                            pos_odds_team_need = NO_NEED
                        else:
                            pos_odds_team_need = BACKUP_WHILE_NEED_STARTER
                else:
                    if pos in max_pos:
                        pos_odds_team_need = NO_NEED
                    else:
                        pos_odds_team_need = NEED_BACKUP
    
                # Position odds based on league - draft data dict league position counts against current round position counts
                scale2 = league_draft_data['LEAGUE']['STDEV'][pos][round_string] \
                        if isinstance(league_draft_data['LEAGUE']['STDEV'][pos][round_string], float) \
                        and league_draft_data['LEAGUE']['STDEV'][pos][round_string] > 0.001 else 0.001
                pos_odds_league_pos_counts = norm.sf(x=pos_counts_this_round[pos] + 1, 
                                                      loc=league_draft_data['LEAGUE']['AVG'][pos][round_string], 
                                                      scale=scale2)
                    
                product = pos_odds_team_end_pos_counts * pos_odds_team_need * pos_odds_league_pos_counts
                total_odds += product
                raw_pos_odds[pos] = product
    
            # Normalize: odds = 1 that a position will be drafted
            pos_odds = {pos: raw / total_odds for pos, raw in raw_pos_odds.items()}
    
            # Player odds based on current pick, ovr avg, ovr std, pos avg, and pos std
            total_odds = {}
            raw_player_odds = {}
    
            pos_cts = {}
            for player in queue.heap:
                pos = player.pos
                if pos not in pos_cts:
                    pos_cts[pos] = 1
                else:
                    pos_cts[pos] += 1
    
                id = player.id
                
                if rd < 16 and pos_cts[pos] > 12:
                
                    # Assume the queue order ovr rk is the same as the pos rk order
                    raw_player_odds[id] = {'PRODUCT': 0}
                    raw_player_odds[id]['POS'] = pos
                    if pos not in total_odds:
                        total_odds[pos] = 0
                    continue
                
                player_pos_odds = norm.cdf(x=league_pos_counts[pos] + 1, loc=player.pos_avg, 
                                            scale=max(player.pos_std, 0.001))
    
                adp_gap = league_pos_counts[pos] - player.pos_adp
                adp_multiplier = math.exp(math.tanh(adp_gap / K) * C)
    
                product = player_pos_odds * adp_multiplier  
    
                if pos not in total_odds:
                    total_odds[pos] = 0
                total_odds[pos] += product
                
                raw_player_odds[id] = {'PRODUCT': product} 
                raw_player_odds[id]['POS'] = pos
    
            player_odds = {
                id: (info['PRODUCT'] / total_odds[info['POS']] if total_odds.get(info['POS'], 0) > 0 else 0.0)
                for id, info in raw_player_odds.items()
            }
    
            return pos_odds, player_odds
    

    def initialize(self, user: str) -> DraftState:
        blackboard = self.blackboard
        queue = NextUpQueue()

        keeper_names = set()
        if blackboard.keepers is not None:
            for v in blackboard.keepers.values():
                if v.get('NAME'):
                    keeper_names.add(v['NAME'])

        for name, data in blackboard.player_data_dict.items():
            if name in keeper_names or 'OVR RK' not in data:
                continue
            queue.push(Player(name, data))

        pos_counts_by_owner = {}
        players_drafted_by_owner = {}
        for owner in blackboard.order:
            pos_counts_by_owner[owner] = {pos: 0 for pos in POS_LIST}
            players_drafted_by_owner[owner] = []
 
            if blackboard.keepers is not None and owner in blackboard.keepers:
                keeper_name = blackboard.keepers[owner].get('NAME', '')
                if keeper_name and keeper_name in blackboard.player_data_dict:
                    pos = blackboard.player_data_dict[keeper_name]['POS']
                    pos_counts_by_owner[owner][pos] = 1
                    players_drafted_by_owner[owner].append(keeper_name)

        pos_counts_by_owner['LEAGUE'] = {pos: 0 for pos in POS_LIST}
        players_drafted_by_owner['LEAGUE'] = []

        return DraftState(
            draft_order=blackboard.order,
            keepers=blackboard.keepers or {},
            total_rounds=blackboard.final_round,
            user=user,
            next_up_queue=queue,
            players_drafted_by_owner=players_drafted_by_owner,
            pos_counts_by_owner=pos_counts_by_owner,
            pos_counts_this_round={pos: 0 for pos in POS_LIST},
            last_round_pos_counts_this_round=None,
            current_round=1,
            current_pick_in_round=1,
            current_pick_overall=1,
            current_pick_owner=blackboard.order[0],
            in_progress=True,
            action_log=[],
            pos_odds={pos: 0.0 for pos in POS_LIST},
            simulation_results=None,
            logical_pick=None,
            probabilistic_pick=None,
            gemini_pick=None,
            gemini_reasoning=None,
            final_pick=None,
        )


    def update_odds(self, state: DraftState) -> dict:
        pos_odds, player_odds = self._calculate_odds(state)
        state['next_up_queue'].update_odds(player_odds)
        return {'pos_odds': pos_odds}

        # For the time being, there is no reason to sort the queue by odds - leave it sorted by overall rank


    def draft_player(self, player_name: str, state: DraftState, keeper_pick: bool=False) -> dict:
        queue = state['next_up_queue']
        player = queue.name_to_player_map[player_name]

        if not keeper_pick:
            queue.pop(player_name)

        owner = state['current_pick_owner']
        rd = state['current_round']
        pick_in_rd = state['current_pick_in_round']
        n_teams = len(state['draft_order'])
 
        action = f'Pick {rd}.{pick_in_rd}: {owner} drafts {player.name}, {player.pos}'
 
        # Update counts
        new_pos_counts_by_owner = {
            o: dict(counts) for o, counts in state['pos_counts_by_owner'].items()
        }
        new_pos_counts_by_owner[owner][player.pos] += 1
        new_pos_counts_by_owner['LEAGUE'][player.pos] += 1
 
        new_pos_counts_this_round = dict(state['pos_counts_this_round'])
        new_pos_counts_this_round[player.pos] += 1
 
        new_players_drafted = {
            o: list(names) for o, names in state['players_drafted_by_owner'].items()
        }
        new_players_drafted[owner].append(player.name)
        new_players_drafted['LEAGUE'].append(player)
 
        # Advance trackers
        new_pick_overall = state['current_pick_overall'] + 1
        new_pick_in_round = state['current_pick_in_round'] + 1
        new_round = state['current_round']
        new_in_progress = state['in_progress']
        last_round_pos_counts = state['last_round_pos_counts_this_round']
 
        if new_pick_in_round > n_teams:
            new_pick_in_round = 1
            new_round += 1
            last_round_pos_counts = new_pos_counts_this_round
            new_pos_counts_this_round = {pos: 0 for pos in POS_LIST}
            if new_round > state['total_rounds']:
                new_in_progress = False
 
        # Next owner
        if new_round % 2 != 0:
            new_owner = state['draft_order'][new_pick_in_round - 1]
        else:
            new_owner = state['draft_order'][n_teams - new_pick_in_round]
 
 
        return {
            'players_drafted_by_owner': new_players_drafted,
            'pos_counts_by_owner': new_pos_counts_by_owner,
            'pos_counts_this_round': new_pos_counts_this_round,
            'last_round_pos_counts_this_round': last_round_pos_counts,
            'current_round': new_round,
            'current_pick_in_round': new_pick_in_round,
            'current_pick_overall': new_pick_overall,
            'current_pick_owner': new_owner,
            'in_progress': new_in_progress,
            'action_log': state['action_log'] + [action],
        }


    def undraft_last_player(self, state: DraftState) -> dict:
            queue = state['next_up_queue']
            last_player = state['players_drafted_by_owner']['LEAGUE'][-1]
            last_player_name = last_player.name
    
            # Restore player to queue
            is_keeper = False
            if state['keepers']:
                for owner, info in state['keepers'].items():
                    if info.get('NAME') == last_player_name:
                        is_keeper = True

            if not is_keeper:
                queue.push(last_player)
                queue.sort_queue()
            else:
                # Keeper pick
                pass
    
            player = queue.name_to_player_map[last_player_name]
    
            # Roll back trackers
            n_teams = len(state['draft_order'])
            new_pick_overall = state['current_pick_overall'] - 1
            new_pick_in_round = state['current_pick_in_round'] - 1
            new_round = state['current_round']
            new_pos_counts_this_round = dict(state['pos_counts_this_round'])
            last_round_counts = state['last_round_pos_counts_this_round']
    
            if new_pick_in_round < 1:
                new_pick_in_round = n_teams
                new_round -= 1
                new_pos_counts_this_round = dict(last_round_counts) if last_round_counts else {pos: 0 for pos in POS_LIST}
                last_round_counts = None
            else:
                new_pos_counts_this_round[player.pos] -= 1
    
            if new_round % 2 != 0:
                new_owner = state['draft_order'][new_pick_in_round - 1]
            else:
                new_owner = state['draft_order'][n_teams - new_pick_in_round]
    
            new_pos_counts_by_owner = {
                o: dict(counts) for o, counts in state['pos_counts_by_owner'].items()
            }
            new_pos_counts_by_owner[new_owner][player.pos] -= 1
            new_pos_counts_by_owner['LEAGUE'][player.pos] -= 1
    
            new_players_drafted = {
                o: list(names) for o, names in state['players_drafted_by_owner'].items()
            }
            new_players_drafted[new_owner].pop()
            new_players_drafted['LEAGUE'].pop()
    
            action = (f'Undo pick {new_round}.{new_pick_in_round}: '
                    f'{new_owner} un-drafts {player.name}, {player.pos}')
    
            return {
                'players_drafted_by_owner': new_players_drafted,
                'pos_counts_by_owner': new_pos_counts_by_owner,
                'pos_counts_this_round': new_pos_counts_this_round,
                'last_round_pos_counts_this_round': last_round_counts,
                'current_round': new_round,
                'current_pick_in_round': new_pick_in_round,
                'current_pick_overall': new_pick_overall,
                'current_pick_owner': new_owner,
                'in_progress': True,
                'action_log': state['action_log'] + [action],
            }       

    
    def make_random_pick(self, state: DraftState) -> dict: 
        queue = state['next_up_queue']
        random_number = random.random()
        random_number1 = random.random()
        lower_bound = 0
        
        for pos in POS_LIST:
            upper_bound =  lower_bound + state['pos_odds'][pos]
            if lower_bound < random_number < upper_bound:
                # Draft this position
                lower_bound1 = 0.0
                for player in queue.heap:
                    if player.pos != pos:
                        continue

                    upper_bound1 = lower_bound1 + player.odds
                    if lower_bound1 < random_number1 < upper_bound1:
                        # Draft this player
                        return self.draft_player(player.name, state)
                    # Update
                    lower_bound1 = upper_bound1

            # Update
            lower_bound = upper_bound

        # Fallback: draft best available
        return self.draft_player(queue.heap[0].name, state)


    def run_simulation(self, state: DraftState) -> dict:
        from draft_functionality import run_all_simulations, add_player_info
 
        queue = state['next_up_queue']
        n_teams = len(state['draft_order'])
        pick_in_round = state['current_pick_in_round']
 
        if pick_in_round == n_teams:
            picks_before_next = (n_teams - 1) * 2 + 1
        else:
            picks_before_next = (n_teams - pick_in_round) * 2 + 1
 
        sim_player_counts = {}
        for player in queue.heap[:100]:
            sim_player_counts[player.name] = {
                'count': 0,
                'POS': player.pos,
                'TEAM': player.team,
                'OVR_RK': player.ovr_rk,
            }
            if player.name in self.blackboard.additional_data_dict:
                sim_player_counts = add_player_info(
                    sim_player_counts, player, self.blackboard)
 
        sim_player_counts = run_all_simulations(
            sim_player_counts, picks_before_next, state, self.blackboard)
 
        sim_player_counts = dict(sorted(
            sim_player_counts.items(),
            key=lambda item: item[1]['OVR_RK']
        ))
 
        return {'simulation_results': sim_player_counts}
 
    def get_next_up_dict(self, state: DraftState) -> dict:
        queue = state['next_up_queue']
        is_last_round = state['current_round'] == state['total_rounds']
        sim_results = state.get('simulation_results') or {}
        next_up = {}
 
        for player in queue.heap:
            count = sim_results.get(player.name, {}).get('count', 0)
            entry = {
                'POS': player.pos,
                'TEAM': player.team,
                'OVR_RK': player.ovr_rk,
                'count': 0 if is_last_round else (count if sim_results else None),
            }
            if player.name in self.blackboard.additional_data_dict:
                d = self.blackboard.additional_data_dict[player.name]
                entry.update({
                    'PROJ_AVG': d.get('ProjAvg'),
                    'L_OUT':    d.get('OutLast'),
                    'L_ISHELP': d.get('IsHelp'),
                    'L_NHELP':  d.get('NeedHelp'),
                    'OL_TIER':  d.get('OLTier'),
                    'INJ_RISK': d.get('InjRisk'),
                    'PRJ_OUT':  d.get('ProjOut'),
                    'PRJ_PPR':  d.get('ProjPPR'),
                    'INJURY':   d.get('Injury'),
                })
            next_up[player.name] = entry
 
        return next_up


class PickleCheckpointer(BaseCheckpointSaver):
    def __init__(self):
        super().__init__()
        self._storage: dict = {}
        self._writes: dict = {}

    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        thread_id = config['configurable']['thread_id']
        if thread_id not in self._storage:
            return None
        return self._storage[thread_id]

    def list(self, config: dict, **kwargs) -> Iterator[CheckpointTuple]:
        thread_id = config['configurable']['thread_id']
        if thread_id in self._storage:
            yield self._storage[thread_id]

    def put(self, config: dict, checkpoint: Checkpoint,
            metadata: CheckpointMetadata, new_versions: dict) -> dict:
        thread_id = config['configurable']['thread_id']
        checkpoint_copy = pickle.loads(pickle.dumps(checkpoint))
        self._storage[thread_id] = CheckpointTuple(
            config=config,
            checkpoint=checkpoint_copy,
            metadata=metadata,
            parent_config=None,
        )
        return config

    def put_writes(self, config: dict, writes: list, task_id: str) -> None:
        # Pending writes between checkpoints - store but don't need to persist
        thread_id = config['configurable']['thread_id']
        if thread_id not in self._writes:
            self._writes[thread_id] = []
        self._writes[thread_id].extend(writes)


# Graph Helpers
def is_my_turn(state: DraftState) -> str:
    total_picks = len(state['draft_order']) * state['total_rounds']
    if not state['in_progress']:
        return 'done'
    
    owner = state['current_pick_owner']
    current_round = state['current_round']

    if state['keepers'] and owner in state['keepers'] and current_round == state['keepers'][owner]['ROUND']:
        return 'keeper_pick'

    my_name = state['user']
    return 'my_turn' if owner == my_name else 'opponent_turn'


# Nodes
def make_keeper_pick_node(engine: DraftEngine):
    def keeper_pick(state: DraftState) -> dict:
        owner = state['current_pick_owner']
        keeper_name = state['keepers'][owner]['NAME']
        return engine.draft_player(keeper_name, state, keeper_pick=True)
    return keeper_pick

def make_update_odds_node(engine: DraftEngine):
    def update_odds(state: DraftState) -> dict:
        return engine.update_odds(state)
    return update_odds

def make_opponent_turn_node(engine: DraftEngine):
    def opponent_turn(state: DraftState) -> dict:
        return engine.make_random_pick(state)
    return opponent_turn

def make_run_agents_node(engine: DraftEngine, ui_queue=None, use_ai: bool=False):
    def run_agents(state: DraftState) -> dict:
        from agents import LogicalDraftAgent, ProbabilisticDraftAgent, gemini_recommendation, eval_fuzzy_matches
        results = {
                    'logical_pick': None,
                    'probabilistic_pick': None,
                    'gemini_pick': None,
                    'gemini_reasoning': '',
                    'simulation_results': None
                }

        def run_simulation():
            try:
                is_last_round = state['current_round'] == state['total_rounds']
                if is_last_round:
                    if ui_queue is not None:
                        ui_queue.put(('next_up', engine.get_next_up_dict(state)))
                    return
                result = engine.run_simulation(state)
                results['simulation_results'] = result['simulation_results']
                if ui_queue is not None:
                    next_up = engine.get_next_up_dict(
                        {**state, 'simulation_results': results['simulation_results']})
                    ui_queue.put(('next_up', next_up))
            except Exception as e:
                print(f'Simulation error: {e}')
                if ui_queue is not None:
                    ui_queue.put(('next_up', engine.get_next_up_dict(state)))
        
        def run_logical():
            try:
                player = LogicalDraftAgent(engine.blackboard).choose_player_to_draft(state)
                results['logical_pick'] = player.name if player else None
            except Exception as e:
                print(f'Logical agent error: {e}')
 
        def run_probabilistic():
            try:
                player = ProbabilisticDraftAgent().choose_player_to_draft(state)
                results['probabilistic_pick'] = player.name if player else None
            except Exception as e:
                print(f'Probabilistic agent error: {e}')
 
        def run_gemini():
            if not use_ai:
                return
            try:
                gemini_result = gemini_recommendation(state)
                name = gemini_result['gemini_pick']
                try:
                    name = eval_fuzzy_matches(name, state['next_up_queue'])
                except ValueError:
                    pass
                results['gemini_pick'] = name
                results['gemini_reasoning'] = gemini_result['gemini_reasoning']
            except Exception as e:
                print(f'Gemini agent error: {e}')
 
        threads = [
            threading.Thread(target=run_simulation, daemon=True),
            threading.Thread(target=run_logical, daemon=True),
            threading.Thread(target=run_probabilistic, daemon=True),
            threading.Thread(target=run_gemini, daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
 
        if ui_queue is not None:
            ui_queue.put(('agent_picks', {
                'logical':      results['logical_pick'],
                'probabilistic': results['probabilistic_pick'],
                'gemini':       results['gemini_pick'],
                'reasoning':    results['gemini_reasoning'],
            }))
 
        return results
    return run_agents

def make_present_picks_node(ui_queue=None):
    def present_picks(state: DraftState) -> dict:
        return {}
    return present_picks
 
def make_record_my_pick_node(engine: DraftEngine, ui_queue=None, user_choice_queue=None):
    def record_my_pick(state: DraftState) -> dict:
        if ui_queue is not None and user_choice_queue is not None:
            # my_pick already sent by _wait_for_pick before interrupt
            player_name = user_choice_queue.get()
        else:
            player_name = input('Your pick: ').strip()

        update = engine.draft_player(player_name, state)
        update['final_pick'] = player_name
        return update
    return record_my_pick


def build_draft_graph(engine: DraftEngine, ui_queue=None, user_choice_queue=None, use_ai=False):

    memory = PickleCheckpointer()
    graph = StateGraph(DraftState)

    
    graph.add_node('update_odds', make_update_odds_node(engine))
    graph.add_node('check_turn', lambda state: {})
    graph.add_node('opponent_turn', make_opponent_turn_node(engine))
    graph.add_node('keeper_pick', make_keeper_pick_node(engine))
    graph.add_node('run_agents', make_run_agents_node(engine, ui_queue, use_ai=use_ai))
    graph.add_node('present_picks', make_present_picks_node(ui_queue))
    graph.add_node('record_my_pick', make_record_my_pick_node(engine, ui_queue, user_choice_queue))
 
    graph.set_entry_point('update_odds')
 
    graph.add_conditional_edges('check_turn', is_my_turn, {
        'my_turn': 'run_agents',
        'opponent_turn': 'opponent_turn',
        'keeper_pick': 'keeper_pick',
        'done': END,
    })
 
    # Opponent and keeper picks
    graph.add_edge('opponent_turn', 'update_odds')
    graph.add_edge('keeper_pick', 'update_odds')
 
    # User turn
    graph.add_edge('update_odds', 'check_turn')
    graph.add_edge('run_agents', 'present_picks')
    graph.add_edge('present_picks', 'record_my_pick')
    graph.add_edge('record_my_pick', 'update_odds')
 
    return graph.compile(
        checkpointer=memory,
        interrupt_before=['record_my_pick'],
    )


# class SimBlackboard(DraftBlackboard):
#     '''Temporary blackboard for simulation workers to avoid serialization issues'''

#     def update_odds(self) -> None:
#         # Build a minimal DraftState-like object to pass to DraftEngine._calculate_odds
#         from infrastructure import DraftEngine
#         engine = DraftEngine(self)
#         # Reconstruct enough of state for _calculate_odds
#         state = {
#             'current_pick_owner': self.current_pick_owner,
#             'current_round': self.current_round,
#             'total_rounds': self.final_round,
#             'pos_counts_by_owner': self.pos_counts_by_owner,
#             'pos_counts_this_round': self.pos_counts_this_round,
#             'next_up_queue': self.next_up_queue,
#         }
#         pos_odds, player_odds = engine._calculate_odds(state)
#         self.pos_odds = pos_odds
#         self.next_up_queue.update_odds(player_odds)

#     def make_random_pick(self, print_picks: bool = False) -> None:
#         import random
#         random_number = random.random()
#         random_number1 = random.random()
#         lower_bound = 0.0

#         for pos in POS_LIST:
#             upper_bound = lower_bound + self.pos_odds[pos]
#             if lower_bound < random_number < upper_bound:
#                 lower_bound1 = 0.0
#                 for player in self.next_up_queue.heap:
#                     if player.pos != pos:
#                         continue
#                     upper_bound1 = lower_bound1 + player.odds
#                     if lower_bound1 < random_number1 < upper_bound1:
#                         self._sim_draft_player(player)
#                         if self.in_progress:
#                             self.update_odds()
#                         return
#                     lower_bound1 = upper_bound1
#             lower_bound = upper_bound

#         # Fallback
#         self._sim_draft_player(self.next_up_queue.heap[0])
#         if self.in_progress:
#             self.update_odds()

#     def _sim_draft_player(self, player: Player) -> None:
#         self.next_up_queue.pop(player.name)
#         self.players_drafted_by_owner[self.current_pick_owner].append(player.name)
#         self.players_drafted_by_owner['LEAGUE'].append(player)
#         self.pos_counts_by_owner[self.current_pick_owner][player.pos] += 1
#         self.pos_counts_by_owner['LEAGUE'][player.pos] += 1
#         self.pos_counts_this_round[player.pos] += 1

#         self.current_pick_overall += 1
#         self.current_pick_in_round += 1
#         n_teams = len(self.order)

#         if self.current_pick_in_round > n_teams:
#             self.current_pick_in_round = 1
#             self.current_round += 1
#             self.last_round_pos_counts_this_round = self.pos_counts_this_round
#             self.pos_counts_this_round = {pos: 0 for pos in self.pos_counts_this_round}
#             if self.current_round > self.final_round:
#                 self.in_progress = False

#         if self.current_round % 2 != 0:
#             self.current_pick_owner = self.order[self.current_pick_in_round - 1]
#         else:
#             self.current_pick_owner = self.order[n_teams - self.current_pick_in_round]