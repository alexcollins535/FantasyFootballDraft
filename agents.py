from infrastructure import DraftBlackboard, Player, DraftState, NextUpQueue
from globals import STARTERS_BY_POSITION, FLEX_POSITIONS, POS_LIST

from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI


# Initialize model
model = ChatGoogleGenerativeAI(model='gemini-3.6-flash', timeout=15)


class LogicalDraftAgent:
    # Rules to follow:
    #   Consider keeper a starter from init
    #   No QB in round 1, 2, 3, 4
    #   No TE in round 1, 2
    #   TE in round 3 or 4 if McBride or Bowers available
    #   At least 1 RB in rounds 1 and 2
    #   Key positions: QB, RB, WR, TE, FLEX
    #   No backups before all key positions have starters
    #   Up to 1 backup TE and up to 1 backup QB
    #   No PK or DEF before rd 11, no backups for either

    def __init__(self, blackboard: DraftBlackboard):
        self.blackboard = blackboard

    def _consider_position_logic(self, state: DraftState):
        owner = state['current_pick_owner']
        pos_counts = state['pos_counts_by_owner'][owner]
        current_round = state['current_round']
        final_round = state['total_rounds']
        available_players = set(state['next_up_queue'].name_to_player_map.keys())

        missing_pos = set()
        missing_n_starters = 0
        flex_excess = 0
        for pos, n_starters in STARTERS_BY_POSITION.items():
            if pos == 'FLEX':
                # Evluate everything else first
                continue

            elif pos_counts[pos] < n_starters:
                missing_pos.add(pos)
                missing_n_starters += (n_starters - pos_counts[pos])

            elif pos_counts[pos] > n_starters and pos in FLEX_POSITIONS:
                # Excess of players for a flex position
                flex_excess += (pos_counts[pos] - n_starters)

        if flex_excess == 0:
            missing_pos.update(set(FLEX_POSITIONS))

        # Late flag - if all remaining picks need to be filled by starters
        if (final_round - current_round) + 1 <= missing_n_starters:
            late_flag = True
        else:
            late_flag = False

        starters_filled_except_pk_def = missing_pos.issubset({'PK', 'DEF'})

        # missing_pos is the set of positions to consider
        consider_set = missing_pos.copy()

        # Rules by position
        if 'QB' not in missing_pos:
            if not late_flag and starters_filled_except_pk_def and pos_counts['QB'] < 2:
                consider_set.add('QB')
        elif current_round < 5:
            consider_set.discard('QB')

        if 'RB' not in missing_pos:
            if not late_flag and starters_filled_except_pk_def:
                consider_set.add('RB')

        if 'WR' not in missing_pos:
            if not late_flag and starters_filled_except_pk_def and not (current_round == 2 and pos_counts['WR'] == 1):
                consider_set.add('WR')

        if 'TE' not in missing_pos:
            if not late_flag and starters_filled_except_pk_def and pos_counts['TE'] < 2:
                consider_set.add('TE')
        elif current_round < 5 and not ('Trey McBride' in available_players or 'Brock Bowers' in available_players):
            consider_set.discard('TE')

        if 'PK' in missing_pos and current_round < 11:
            consider_set.discard('PK')

        if 'DEF' in missing_pos and current_round < 11:
            consider_set.discard('DEF')

        return consider_set

    def choose_player_to_draft(self, state: DraftState) -> Player:
        ''' Simply choose the player with the best my_rank within the positions considered '''

        consider_pos_set = self._consider_position_logic(state)

        best = (None, None)
        
        for player in state['next_up_queue'].heap:
            if player.pos not in consider_pos_set or player.name not in self.blackboard.additional_data_dict.keys():
                # Don't consider position or unranked players
                continue

            my_rank = self.blackboard.additional_data_dict[player.name]['MyRank']

            if best[0] is None or best[0] > my_rank:
                best = (my_rank, player)
            
        return best[1]


class ProbabilisticDraftAgent:
    def __init__(self):
        pass

    def choose_player_to_draft(self, state: DraftState) -> Player: 
        '''Pick the player with the highest product of position and player odds'''
        best = (0, None)
        
        for pos in POS_LIST:
            for player in state['next_up_queue'].heap:
                if player.pos != pos:
                    continue

                product = state['pos_odds'][pos] * player.odds
                    
                if product > best[0]:
                    best = (product, player)

        return best[1]




def format_draft_board(state: DraftState) -> str:
    lines = []
    for i, player in enumerate(state['players_drafted_by_owner']['LEAGUE']):
        # Find owner by checking per-owner lists
        owner = next(
            o for o, names in state['players_drafted_by_owner'].items()
            if o != 'LEAGUE' and player.name in names
        )
        lines.append(f'  Pick {i+1:>3} ({owner}): {player.name} ({player.pos})')
    return '\n'.join(lines)


def format_roster(state: DraftState) -> str:
    user = state['user']
    my_players = [p for p in state['players_drafted_by_owner']['LEAGUE']
                  if p.name in state['players_drafted_by_owner'][user]]
    if not my_players:
        return 'Empty - no picks yet'
    return '\n'.join(f'  {p.pos}: {p.name}' for p in my_players)


def format_keepers(keepers: dict) -> str:
    if not keepers:
        return 'None'
    lines = [f'  {owner}: {k['NAME']} ({k['POS']}, kept in Rd {k['ROUND']})'
             for owner, k in keepers.items()]
    return '\n'.join(lines)


def gemini_recommendation(state: DraftState) -> dict:
    pick_number = state['current_pick_overall']
    round_number = state['current_round']

    prompt = f'''
    You are an expert fantasy football draft assistant for a team in 12-team PPR league 
    in the 2026-27 NFL season.

    CURRENT PICK: #{state['current_pick_overall']} (Round {state['current_round']})

    MY CURRENT ROSTER:
    {format_roster(state)}

    FULL DRAFT BOARD SO FAR (all picks in order):
    {format_draft_board(state)}

    KEEPERS (removed before draft began):
    {format_keepers(state['keepers'])}

    Roster requirements: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 DEF, 1 PK - 16 rounds total.
    Keeper requirements: owner forfeits their draft pick for the round a player is kept 
    in (e.g. if Drake Maye is kept in round 12, the owner does not pick another player 
    in round 12).

    Based on my roster construction and the draft trends you observe, respond in exactly 
    this format and no other:
    PICK: [player name]
    REASON: [3-4 sentence explanation covering positional need, roster construction, 
    and draft trends you observe from the board]
    '''

    response = model.invoke(prompt)
    text = response.content if isinstance(response.content, str) else response.content[0].text
    lines = text.strip().split('\n')
    pick_line = next(l for l in lines if l.startswith('PICK:'))
    reason_line = next((l for l in lines if l.startswith('REASON:')), None)

    player_name = pick_line.replace('PICK:', '').strip()
    reasoning = reason_line.replace('REASON:', '').strip() if reason_line else ''

    return {'gemini_pick': player_name, 'gemini_reasoning': reasoning}




def eval_fuzzy_matches(pick, queue: NextUpQueue) -> str:
    def check_if_name_in_queue(name):
        return name in queue.name_to_player_map.keys()
    
    def try_suffixes(name):
        for suffix in [' Sr.', ' Jr.', ' II', ' III']:
            name_to_check = pick + suffix
            if check_if_name_in_queue(name_to_check):
                return name_to_check
        return None
    
    # Raw pick
    if check_if_name_in_queue(pick):
        return pick

    # Raw with suffix
    new_name = try_suffixes(pick)
    if new_name:
        return new_name

    # Add or remove punctuation
    names = pick.split(' ')
    if '.' in names[0]:
        names[0] = names[0].replace('.', '')
    elif len(names[0]) == 2:
        names[0] = names[0][0] + '.' + names[0][1] + '.'

    modified_name = ' '.join(names)
    if modified_name != pick:
        if check_if_name_in_queue(modified_name):
            return modified_name

        new_name = try_suffixes(modified_name)
        if new_name:
            return new_name


    elif names[0] in ('Ken', 'Kenny', 'Kenneth'):
        for eval_name in ('Ken', 'Kenny', 'Kenneth'):
            if eval_name == names[0]:
                continue

            if check_if_name_in_queue(eval_name):
                        return eval_name
            
            new_name = try_suffixes(eval_name)
            if new_name:
                return new_name
            
    elif names[0] in ('Cam', 'Cameron'):
        for eval_name in ('Cam', 'Cameron'):
            if eval_name == names[0]:
                continue

            if check_if_name_in_queue(eval_name):
                        return eval_name
            
            new_name = try_suffixes(eval_name)
            if new_name:
                return new_name
    
    elif names[0] in ('Bill', 'Jacory'):
        for eval_name in ('Bill', 'Jacory'):
            if eval_name == names[0]:
                continue

            if check_if_name_in_queue(eval_name):
                        return eval_name
            
            new_name = try_suffixes(eval_name)
            if new_name:
                return new_name
        
        
    # No matches found
    raise ValueError(f'Cannot find match for gemini pick: {pick}')
