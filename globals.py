import time

# League Basic Info
LEAGUES = ['DEFAULT', 'Smithfield', 'Fox Run']

DEFAULT_OWNERS = ['player1', 'player2', 'player3', 'player4', 'player5', 'player6', 'player7', 'player8', 'player9', 'player10', 'player11', 'player12']
DEFAULT_DRAFT_ORDER = None

FOX_RUN_OWNERS = ['Alex', 'Christian', 'Cole', 'Duz', 'Jeff', 'Kev', 'Mas', 'Matt', 'Owen P', 'Owen S', 'Shawn', 'Zach']
FOX_RUN_DRAFT_ORDER = ['Matt', 'Zach', 'Cole', 'Kev', 'Duz', 'Alex', 'Owen S', 'Owen P', 'Mas', 'Shawn', 'Christian', 'Jeff']

SMITHFIELD_OWNERS = ['Alex', 'Christian', 'Mack', 'Duz', 'JT', 'Nico', 'Erbe', 'Matt', 'Kyle', 'Owen S', 'Ryan', 'Zach']
SMITHFIELD_DRAFT_ORDER = ['Alex', 'JT', 'Mack', 'Zach', 'Christian', 'Ryan', 'Erbe', 'Matt', 'Nico', 'Duz', 'Owen S', 'Kyle']
SMITHFIELD_KEEPERS = {
    'Alex':         {'NAME': 'Drake Maye', 'ROUND': 12, 'POS': 'QB'},            # Secondary: Quinshon Judkins in 9
    'Christian':    {'NAME': 'Travis Etienne Jr.', 'ROUND': 8, 'POS': 'RB'},     # Secondary: Bhayshul Tuten in 7
    'Mack':         {'NAME': 'Drake London', 'ROUND': 2, 'POS': 'WR'},           
    'Duz':          {'NAME': 'Chris Godwin Jr.', 'ROUND': 9, 'POS': 'WR'},       # Secondary: Rico Dowdle in 12
    'JT':           {'NAME': 'Colston Loveland', 'ROUND': 9, 'POS': 'TE'},       
    'Nico':         {'NAME': 'Chris Olave', 'ROUND': 6, 'POS': 'WR'},            # Secondary: Tyler Warren in 7
    'Erbe':         {'NAME': 'Rashee Rice', 'ROUND': 5, 'POS': 'WR'},            # Secondary: Tetairoa McMillan in 4
    'Matt':         {'NAME': 'Cam Skattebo', 'ROUND': 10, 'POS': 'RB'},          # Secondary: Javonte Williams in 8
    'Kyle':         {'NAME': 'Emeka Egbuka', 'ROUND': 6, 'POS': 'WR'},           
    'Owen S':       {'NAME': 'Rome Odunze', 'ROUND': 6, 'POS': 'WR'},            # Secondary: Harold Fannin Jr. in 8
    'Ryan':         {'NAME': 'George Pickens', 'ROUND': 4, 'POS': 'WR'},
    'Zach':         {'NAME': 'Justin Herbert', 'ROUND': 14, 'POS': 'QB'}
}

# Update map upon adding new leagues
LEAGUE_TO_GLOBALS = {
            'Smithfield': {'OWNERS': SMITHFIELD_OWNERS, 'KEEPERS': SMITHFIELD_KEEPERS, 'ORDER': SMITHFIELD_DRAFT_ORDER},
            'Fox Run': {'OWNERS': FOX_RUN_OWNERS, 'KEEPERS': None, 'ORDER': FOX_RUN_DRAFT_ORDER},
            'DEFAULT': {'OWNERS': DEFAULT_OWNERS, 'KEEPERS': None, 'ORDER': DEFAULT_DRAFT_ORDER}
        }


# Random seeds
SEED = 7   
RANDOMIZED_SEED = int(time.time())

# Data Preprocessing Globals
REF_FILEPATH = 'FFL_Reference.xlsx'
POS_RK_SHEET = 'pos_rk'
OVR_RK_SHEET = 'ovr_rk'
PAST_DRAFT_SHEET = 'past_draft_by_round'
DRAFT_BY_TEAM_SHEET = 'ct_draft_by_team'
ADDITIONAL_DATA_SHEET = 'my_stats'
PLAYER_DATA_JSON = 'player_data.json'
DRAFT_DATA_JSON = 'draft_data.json'
ADDITIONAL_DATA_JSON = 'additional_data.json'

# Standard Settings
POS_LIST = ['QB', 'RB', 'WR', 'TE', 'DEF', 'PK']
DRAFT_ROUNDS = 16 
STARTERS_BY_POSITION = {'QB': 1, 'RB': 2, 'WR': 2, 'TE': 1, 'FLEX': 1, 'DEF': 1, 'PK': 1}
FLEX_POSITIONS = ['RB', 'WR', 'TE']

# Position Need Globals
NEED_STARTER = 1.0
BACKUP_WHILE_NEED_STARTER = 0.1
NEED_BACKUP = 0.5
NO_NEED = 0.0
MAX_BY_POS = {
    'QB': 2,
    'RB': 10,
    'WR': 10,
    'TE': 2,
    'PK': 1,
    'DEF': 2
}

# Data cleaning defaults
OVR_AVG_DEFAULT = 500
POS_AVG_DEFAULT = 200
STD_DEFAULT = 1

# For in draft simulation functuionality
N_SIMULATIONS = 32
N_WORKERS = 8

# Positional ADP TANH parameters
K = 5.0
C = 1.0
