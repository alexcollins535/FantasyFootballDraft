from preprocessing import get_player_data_dict, get_draft_data_dict, get_additional_data_dict
from globals import (POS_LIST, DRAFT_ROUNDS, STARTERS_BY_POSITION, FLEX_POSITIONS, NEED_STARTER, BACKUP_WHILE_NEED_STARTER, NEED_BACKUP, NO_NEED, 
                     MAX_BY_POS, LEAGUES, LEAGUE_TO_GLOBALS, C, K)

import random
import itertools
from scipy.stats import norm
import math

class DraftBlackboard:
    '''
    Init args:
    - league: Smithfield, Fox Run, or DEFAULT
    - user_selection: boolean, True implies a user will be drafting picks, loads additional player info to be printed

    Callable methods:
    - make_random_pick(): drafts a random player based on rankings, need, owner, and league tendencies
    - make_select_pick(): prompts the user to select a valid player, then drafts them
    - print_results(): prints the drafted players for each owner, sorted by position

    Useful attributes:
    - action_log: stores all individual draft picks made
    - next_up_queue: a NextUpQueue object, its heap is a queue of players sorted by odds to be picked next

    Note: 
    - Modify the __init__ call if adding new leagues
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
        
        players_drafted_by_owner = {}
        pos_counts_this_round = {}
        pos_counts_by_owner = {}
        for owner in order:
            players_drafted_by_owner[owner] = []
            pos_counts_by_owner[owner] = {}
            
            for pos in POS_LIST:
                pos_counts_by_owner[owner][pos] = 0

            if keepers is not None:
                keeper_name = keepers[owner]['NAME']
                players_drafted_by_owner[owner].append(keeper_name)
                pos_counts_by_owner[owner][self.player_data_dict[keeper_name]['POS']] = 1
            
        pos_counts_by_owner['LEAGUE'] = {}
        players_drafted_by_owner['LEAGUE'] = []
        for pos in POS_LIST:
            pos_counts_by_owner['LEAGUE'][pos] = 0
            pos_counts_this_round[pos] = 0

        draft_data = get_draft_data_dict()
        if league not in draft_data.keys():
            league = 'DEFAULT'

        # Late round drop ranking odds when kickers and defenses are being drafted

        self.draft_data_dict = draft_data[league]

        self.league = league
        self.order = order
        self.keepers = keepers

        self.players_drafted_by_owner = players_drafted_by_owner
        self.pos_counts_by_owner = pos_counts_by_owner
        self.pos_counts_this_round = pos_counts_this_round

        self.current_round = 1
        self.current_pick_in_round = 1
        self.current_pick_overall = 1
        self.current_pick_owner = order[0]

        self.last_round = DRAFT_ROUNDS
        self.in_progress = True

        self.next_up_queue = NextUpQueue()
        self.action_log = []
        self.pos_odds = None
        self.last_user_pick = None
        self.last_round_pos_counts_this_round = None


    def _log_player(self, player: Player):
        self.players_drafted_by_owner[self.current_pick_owner].append(player.name)
        self.pos_counts_by_owner[self.current_pick_owner][player.pos] += 1

        self.players_drafted_by_owner['LEAGUE'].append(player)
        self.pos_counts_by_owner['LEAGUE'][player.pos] += 1
        self.pos_counts_this_round[player.pos] += 1


    def _end_draft(self):
        self.action_log.append('The draft has ended.')
        self.in_progress = False


    def _calculate_odds(self) -> dict[int, float]:
        league_draft_data = self.draft_data_dict
        current_pick_owner = self.current_pick_owner
        current_pick_number = self.current_pick_overall
        current_pick_round = self.current_round
        league_pos_counts = self.pos_counts_by_owner['LEAGUE']
        owner_pos_counts = self.pos_counts_by_owner[current_pick_owner]
        pos_counts_this_round = self.pos_counts_this_round

        round_string = f'Round {current_pick_round}'

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
            scale1 = league_draft_data['OWNER_TOTALS'][current_pick_owner][pos]['STD'] \
                    if isinstance(league_draft_data['OWNER_TOTALS'][current_pick_owner][pos]['STD'], float) \
                    and league_draft_data['OWNER_TOTALS'][current_pick_owner][pos]['STD'] > 0.001 else 0.001
            pos_odds_team_end_pos_counts = norm.sf(x=owner_pos_counts[pos] + 1,
                                                    loc=league_draft_data['OWNER_TOTALS'][current_pick_owner][pos]['AVG'], 
                                                    scale=scale1)

            # Position odds based on need - current pick owner position counts
            if missing_pos:
                if pos in missing_pos or ('FLEX' in missing_pos and pos in FLEX_POSITIONS):
                    pos_odds_team_need = NEED_STARTER
                else:
                    if self.last_round - current_pick_round < count_missing:
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

        for player in self.next_up_queue.heap:
            pos = player.pos
            id = player.id
            # plain_pos_odds = pos_odds[pos]
            # player_ovr_odds = norm.cdf(x=current_pick_number + 1, loc=player.ovr_avg, 
            #                             scale=max(player.ovr_std, 0.001))
            player_pos_odds = norm.cdf(x=league_pos_counts[pos] + 1, loc=player.pos_avg, 
                                        scale=max(player.pos_std, 0.001))

            adp_gap = league_pos_counts[pos] - player.pos_adp
            adp_multiplier = math.exp(math.tanh(adp_gap / K) * C)

            product = player_pos_odds * adp_multiplier if player_pos_odds * adp_multiplier  >= 0.01 else 0  


            if pos not in total_odds:
                total_odds[pos] = 0
            total_odds[pos] += product
            
            raw_player_odds[id] = {'PRODUCT': product} 
            raw_player_odds[id]['POS'] = pos

        player_odds = {id: info['PRODUCT'] / total_odds[info['POS']] for id, info in raw_player_odds.items()}

        self.pos_odds = pos_odds
        return player_odds


    def update_odds(self) -> None:
        player_odds = self._calculate_odds()
        self.next_up_queue.update_odds(player_odds)

        # For the time being, there is no reason to sort the queue by odds - leave it sorted by overall rank
        # self.next_up_queue.sort_queue()


    def draft_player(self, player: Player, print_picks: bool, keeper_pick: bool=False) -> None:
        # Log the player
        if not keeper_pick:
            self.next_up_queue.pop(player.name)
        self._log_player(player)
        action_string = f'Pick {self.current_round}.{self.current_pick_in_round}: {self.current_pick_owner} drafts {player.name}, {player.pos}'
        self.action_log.append(action_string)

        if print_picks:
            print(action_string)

        # Move trackers to next pick
        self.current_pick_overall += 1
        self.current_pick_in_round += 1
        if self.current_pick_in_round > 12:
            self.current_pick_in_round = 1
            self.current_round += 1
            self.last_round_pos_counts_this_round = self.pos_counts_this_round
            self.pos_counts_this_round = {pos: 0 for pos in self.pos_counts_this_round.keys()}
            if self.current_round > self.last_round:
                self._end_draft()

        if self.current_round % 2 != 0:
            self.current_pick_owner = self.order[self.current_pick_in_round - 1]
        else:
            # Reverse order
            self.current_pick_owner = self.order[len(self.order) - self.current_pick_in_round]


    def undraft_last_player(self) -> None:
        # Grab the last player
        last_player = self.players_drafted_by_owner['LEAGUE'].pop()

        # Turn back trackers to previous pick
        self.current_pick_overall -= 1
        self.current_pick_in_round -= 1
        if self.current_pick_in_round < 1:
            self.current_pick_in_round = 12
            self.current_round -= 1
            self.pos_counts_this_round = self.last_round_pos_counts_this_round
        else:
            self.pos_counts_this_round[last_player.pos] -= 1

        # Use the order to directly grab the current owner based on the NOW current pick in round
        if self.current_round % 2 != 0:
            self.current_pick_owner = self.order[self.current_pick_in_round - 1]
        else:
            # Reverse order
            self.current_pick_owner = self.order[len(self.order) - self.current_pick_in_round]

        # Unlog the player from league and team counts 
        del self.players_drafted_by_owner[self.current_pick_owner][-1]

        self.pos_counts_by_owner['LEAGUE'][last_player.pos] -= 1
        self.pos_counts_by_owner[self.current_pick_owner][last_player.pos] -= 1

        action_string = f'Undo pick {self.current_round}.{self.current_pick_in_round}: {self.current_pick_owner} drafts {last_player.name}, {last_player.pos}'
        self.action_log.append(action_string)

        # Lastly, re-add this player to queue IF not a keeper pick
        if self.keepers is not None and self.keepers[self.current_pick_owner]['ROUND'] == self.current_round:
            # This is a keeper pick, we're done here
            return

        self.next_up_queue.push(last_player)
        self.next_up_queue.sort_queue()        

        
    
    def make_random_pick(self, print_picks: bool) -> None: 
        random_number = random.random()
        random_number1 = random.random()

        lower_bound = 0
        
        for pos in POS_LIST:
            upper_bound =  lower_bound + self.pos_odds[pos]
            if random_number < upper_bound and random_number > lower_bound:
                # Draft this position
                lower_bound1 = 0
                for player in self.next_up_queue.heap:
                    if player.pos != pos:
                        continue

                    upper_bound1 = lower_bound1 + player.odds
                    if random_number1 < upper_bound1 and random_number1 > lower_bound1:
                        # Draft this player
                        self.draft_player(player, print_picks)
                        if self.in_progress:
                            self.update_odds()
                        return
                    # Update
                    lower_bound1 = upper_bound1

            # Update
            lower_bound = upper_bound


    def make_select_pick(self, draft_type) -> None:
        valid = False
        while not valid:
            name_to_verify = None
            player_input = input(f'\nDraft selection for {self.current_pick_owner}: ')
            if player_input in self.next_up_queue.name_to_player_map:
                name_to_verify = player_input
            else:
                # Loop through the queue for string matches of first and/or last name
                string_for_match = player_input.upper()
                potential_matches = []
                for player in self.next_up_queue.heap:
                    name = player.name.upper()
                    first, last = name.split()[:2]
                    if first in string_for_match or last in string_for_match:
                        potential_matches.append(player.name)

                if len(potential_matches) == 1:
                    name_to_verify = potential_matches[0]

                elif potential_matches:
                    print_string = 'Found matches:'
                    for i, match in enumerate(potential_matches):
                        print_string += f'\n{i+1}. {match}'
                    print(print_string)
                
                    selected = False
                    while not selected:
                        selected_input = input('Enter value of selection (or 0 to go back): ')
                        if selected_input.isdigit():
                            if 0 < int(selected_input) <= len(potential_matches):
                                name_to_verify = potential_matches[int(selected_input) - 1]
                                selected = True
                            if 0 == int(selected_input):
                                self.go_back_to_last_user_pick(draft_type)
                        else:
                            print('Invalid selection.')

                else:
                    # potential_matches is empty
                    print('No matches found.')

            if name_to_verify is not None:
                yn = input(f'Select {name_to_verify}? (y/n): ')
                if yn.lower() in ('y', 'yes', 'n', 'no'):
                    if yn.lower() in ('y', 'yes'):
                        valid = True
                        player_obj = self.next_up_queue.name_to_player_map[name_to_verify]
                        self.draft_player(player_obj, print_picks=True)
                        if self.in_progress:
                            self.update_odds()
                        
                    
    def print_results(self):
        print()
        for owner, players_list in self.players_drafted_by_owner.items():
            if owner == 'LEAGUE':
                continue

            pos_to_player_list = {}
            for player_name in players_list:
                pos = self.player_data_dict[player_name]['POS']
                if pos not in pos_to_player_list:
                    pos_to_player_list[pos] = []
                pos_to_player_list[pos].append(player_name)

            print(f'\nOwner: {owner}')
            for pos in POS_LIST:
                player_list = pos_to_player_list[pos]
                player_string = ',  '.join(player_list)
                print(f'  {pos}: {player_string}')


    def go_back_to_last_user_pick(self, draft_type):
        assert draft_type in ('all select', 'mock draft')
        if draft_type == 'all select':
            self.undraft_last_player()

        else:
            current_user = self.current_pick_owner
            self.undraft_last_player()

            # Rewind until the two match
            while current_user != self.current_pick_owner:
                self.undraft_last_player()

             
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
        self.heap = []
        self.name_to_player_map = {}


    def push(self, player: Player) -> None:
        self.heap.append(player)
        self._bubble_up(len(self.heap) - 1)
        self.name_to_player_map[player.name] = player


    def _bubble_up(self, index):
        while index > 0 and self.heap[index] < self.heap[index-1]:
            # Swap parent and child
            self.heap[index], self.heap[index-1] = self.heap[index-1], self.heap[index]
            index = index-1


    def pop(self, player_name: str) -> None:
        player = self.name_to_player_map.pop(player_name)
        self.heap.remove(player)


    def sort_queue(self):
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


        