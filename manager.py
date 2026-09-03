import threading
import queue as q_module
import random
import pickle
import os
from datetime import datetime

from infrastructure import DraftBlackboard, DraftEngine, DraftState, build_draft_graph
from user_interface import DraftBridge, DraftApp, LoadScreen
from globals import SEED

from dotenv import load_dotenv
load_dotenv()


class AgentDraftWorker:
    '''
    Extend DraftWorker with LangGraph agent recommendations.
    Overrides _ui_select_pick to run agents before prompting user.
    '''

    def __init__(self, bridge: DraftBridge, app: DraftApp, league: str, user: str, draft_type: str, simulation: bool, use_ai: bool=False):

        self.bridge = bridge
        self.app = app
        self.league = league
        self.user = user
        self.draft_type = draft_type
        self.simulation = simulation
        self._user_choice_queue = q_module.Queue()
        self.use_ai = use_ai

    def push(self, cmd, payload=None):
        self.bridge.ui_queue.put((cmd, payload))

    def run(self, load_state=None):
        self.push('status', f'Initializing {self.league} draft...')

        blackboard = DraftBlackboard(self.league, user_selection=True)
        engine = DraftEngine(blackboard)

        if load_state is not None:
            state = self._restore_ui_from_state(load_state, engine)
        else:
            state = engine.initialize(user=self.user)

        graph = build_draft_graph(engine=engine, ui_queue=self.bridge.ui_queue, user_choice_queue=self._user_choice_queue, use_ai=self.use_ai)
        config = {'configurable': {'thread_id': 'draft'}}

        self.push('status', f'Draft started for {self.league}')

        # updates mode -> each loop yields a dictionary representing what one node returned
        # runs until it hits an interrupt (user pick) or END
        for event in graph.stream(state, config, stream_mode='updates'):
            # Handle events that push additional info to the UI
            self._handle_event(event, engine)

        while True:
            snapshot = graph.get_state(config)
            if not snapshot.next:
                break  # reached END
            if 'record_my_pick' in snapshot.next:
                self._wait_for_pick(graph, config, snapshot.values)

        final_state = graph.get_state(config).values
        self._on_draft_done(final_state, engine)

    def _wait_for_pick(self, graph, config, state):
        owner = state['current_pick_owner']
        rd = state['current_round']
        pick = state['current_pick_in_round']

        self.push('load_team', (owner, self.app._owner_teams.get(owner, [])))
        self.push('my_pick', f'{rd}.{pick} Draft selection for {owner}: ')

        while True:
            self.bridge.pick_event.clear()
            self.bridge.pick_event.wait()

            if self.bridge.pending_undo:
                self.bridge.pending_undo = False
                self._handle_undo(graph, config, state)
                return

            raw = (self.bridge.pending_pick or '').strip()
            queue = state['next_up_queue']

            # Name resolution
            if raw in queue.name_to_player_map:
                player_name = raw
            else:
                upper = raw.upper()
                matches = [p.name for p in queue.heap
                           if any(part in upper for part in p.name.upper().split()[:2])]
                if len(matches) == 1:
                    player_name = matches[0]
                elif matches:
                    self.push('status', f'Multiple matches for "{raw}": {", ".join(matches[:5])}. Enter full name.')
                    continue
                else:
                    self.push('status', f'No matches found for "{raw}".')
                    continue

            # Send to graph via queue, record_my_pick node is blocking on this
            self._user_choice_queue.put(player_name)

            player = queue.name_to_player_map.get(player_name)

            # Resume graph
            for event in graph.stream(None, config, stream_mode='updates'):
                self._handle_event(event, None)

            if player:
                self.push('team_pick', (owner, player.pos, player.name))
                if owner == self.user:
                    self._user_pick_count = getattr(self, '_user_pick_count', 0) + 1
                    self.push('undo_enable')
                self.push('status', f'Drafted: {player.name}, {player.pos}')
                self._autosave(graph, config)
            return

    def _restore_ui_from_state(self, state: DraftState, engine: DraftEngine) -> DraftState:
        league_players = {p.name: p for p in state['players_drafted_by_owner']['LEAGUE']}
        for owner, names in state['players_drafted_by_owner'].items():
            if owner == 'LEAGUE':
                continue
            for name in names:
                pos = league_players[name].pos if name in league_players else '?'
                self.push('team_pick', (owner, pos, name))
                if owner == self.user:
                    self._user_pick_count = getattr(self, '_user_pick_count', 0) + 1
        if getattr(self, '_user_pick_count', 0) > 0:
            self.push('undo_enable')
        return state

    def _handle_undo(self, graph, config, state):
        '''Undo by rewinding graph state'''
        from infrastructure import DraftEngine
        snapshot = graph.get_state(config)
        history = list(graph.get_state_history(config))

        if len(history) > 1:
            previous = history[1]
            graph.update_state(config, previous.values)
            self._user_pick_count = max(0, getattr(self, '_user_pick_count', 0) - 1)
            if self._user_pick_count == 0:
                self.push('undo_disable')

            # Rebuild tram panel from this state
            new_state = graph.get_state(config).values

            league_players = {p.name: p for  p in new_state['players_drafted_by_owner']['LEAGUE']}
            updated_picks = [(league_players[name].pos, name)
                for name in new_state['players_drafted_by_owner'][self.user] if name in league_players]

            self.push('undo_team', (self.user, updated_picks))
            self.push('status', 'Pick undone.')

    def _handle_event(self, event: dict, engine):
        '''Extra UI handling for graph node events'''
        # Opponent picks need a team_pick push
        if 'opponent_turn' in event:
            node_output = event['opponent_turn']
            drafted = node_output.get('players_drafted_by_owner', {}).get('LEAGUE', [])
            if drafted:
                player = drafted[-1]  # Player object
                owner = node_output.get('current_pick_owner', '')
                # owner advanced - get previous owner from action_log
                log = node_output.get('action_log', [])
                if log:
                    # Parse: "Pick rd.pick: owner drafts name, pos"
                    try:
                        parts = log[-1].split(': ', 1)[1]
                        prev_owner = parts.split(' drafts ')[0]
                        self.push('team_pick', (prev_owner, player.pos, player.name))
                        self.push('status', log[-1])
                    except Exception:
                        pass

        if 'keeper_pick' in event:
            node_output = event['keeper_pick']
            log = node_output.get('action_log', [])
            if log:
                try:
                    parts = log[-1].split(': ', 1)[1]
                    prev_owner = parts.split(' drafts ')[0]
                    drafted = node_output.get('players_drafted_by_owner', {}).get('LEAGUE', [])
                    if drafted:
                        player = drafted[-1]
                        self.push('team_pick', (prev_owner, player.pos, player.name))
                        self.push('status', f'Keeper: {player.name} ({player.pos}) to {prev_owner}')
                except Exception:
                    pass

    def _on_draft_done(self, state, engine):
            snapshot_state = state
            results_lines = []
            for owner, names in snapshot_state['players_drafted_by_owner'].items():
                if owner == 'LEAGUE':
                    continue
                league_players = {p.name: p for p in snapshot_state['players_drafted_by_owner']['LEAGUE']}
                pos_map: dict[str, list] = {}
                for name in dict.fromkeys(names):
                    pos = league_players[name].pos if name in league_players else '?'
                    pos_map.setdefault(pos, []).append(name)
                results_lines.append(f'\n{owner}')
                for pos in ('QB', 'RB', 'WR', 'TE', 'FLEX', 'DEF', 'PK'):
                    if pos in pos_map:
                        results_lines.append(f'  {pos}: {", ".join(pos_map[pos])}')
            self.push('done', '\n'.join(results_lines))

    def _autosave(self, graph, config):
        '''Autosave current graph state.'''
        date_str = datetime.now().strftime('%Y%m%d')
        path = os.path.join('saved_draft_states',
                            f'{self.league}_{date_str}_autosave.pkl')
        os.makedirs('saved_draft_states', exist_ok=True)
        snapshot = graph.get_state(config)
        with open(path, 'wb') as f:
            pickle.dump(snapshot.values, f)


def _safe_run(worker, load_state):
    try:
        worker.run(load_state)
    except Exception:
        import traceback
        traceback.print_exc()


def launch_agent_ui(league: str, user: str, draft_type: str = 'mock draft',
                    simulation: bool = True):
    saved_dir = 'saved_draft_states'
    load_screen = LoadScreen(saved_dir, league=league, draft_type=draft_type)
    load_screen.mainloop()

    load_state = None
    if load_screen.selected_path is not None:
        with open(load_screen.selected_path, 'rb') as f:
            load_state = pickle.load(f)

    league = load_screen.league_var.get()
    draft_type = load_screen.draft_type_var.get()

    bridge = DraftBridge()
    app = DraftApp(bridge, league=league, user=user,
                   draft_type=draft_type, simulation=simulation)

    use_ai = load_screen.ai_var.get() == 'AI On'

    worker = AgentDraftWorker(bridge, app, league=league, user=user,
                            draft_type=draft_type, simulation=simulation,
                            use_ai=use_ai)

    thread = threading.Thread(target=_safe_run, args=(worker, load_state), daemon=True)
    thread.start()

    app.mainloop()


if __name__ == '__main__':
    random.seed(SEED)
    launch_agent_ui(league='Smithfield', user='Alex', draft_type='mock draft', simulation=True)