import tkinter as tk
from tkinter import ttk
import threading
import queue as q_module
import os 
import sys
from datetime import datetime

from globals import POS_LIST, FLEX_POSITIONS


class DraftBridge:
    def __init__(self):
        self.pick_event = threading.Event()
        self.pending_pick: str | None = None
        self.ui_queue: q_module.Queue = q_module.Queue()
        self.pending_undo: bool = False


class LoadScreen(tk.Tk):
    def __init__(self, saved_dir: str, league: str, draft_type: str):
        super().__init__()
        self.title('Fantasy Draft -- Load')
        self.configure(bg=DraftApp.BG)
        self.resizable(True, True)
        self.selected_path: str | None = None

        tk.Label(self, text='⬡  FANTASY DRAFT', bg=DraftApp.BG, fg=DraftApp.HIGHLIGHT, font=DraftApp.FONT_TITLE, pady=10).pack()

        tk.Label(self, text='Select a saved draft to resume, or start a new one.',
                 bg=DraftApp.BG, fg=DraftApp.FG_DIM, font=DraftApp.FONT_STATUS).pack(pady=(0, 8))

        frame = tk.Frame(self, bg=DraftApp.PANEL)
        frame.pack(fill='both', expand=True, padx=20, pady=(0, 12))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        cols = ['FILE', 'MODIFIED']
        self._tree = ttk.Treeview(frame, columns=cols, show='headings', selectmode='browse')
        self._tree.heading('FILE', text='File')
        self._tree.heading('MODIFIED', text='Last Modified')
        self._tree.column('FILE', width=320, anchor='w')
        self._tree.column('MODIFIED', width=160, anchor='w')

        vsb = ttk.Scrollbar(frame, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')

        self._files = []
        if os.path.isdir(saved_dir):
            for fname in sorted(os.listdir(saved_dir), reverse=True):
                if fname.endswith('.pkl'):
                    full = os.path.join(saved_dir, fname)
                    modified = datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M')
                    self._tree.insert('', 'end', values=(fname, modified))
                    self._files.append(full)

        self._tree.bind('<Double-1>', self._on_double_click)

        btn_frame = tk.Frame(self, bg=DraftApp.BG)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text='Resume Selected', bg=DraftApp.HIGHLIGHT, fg='#ffffff',
                  font=DraftApp.FONT_HEAD, relief='flat', padx=10, pady=4,
                  command=self._resume_selected).pack(side='left', padx=(0, 12))

        tk.Button(btn_frame, text='New Draft', bg=DraftApp.ACCENT, fg=DraftApp.FG,
                  font=DraftApp.FONT_HEAD, relief='flat', padx=10, pady=4,
                  command=self._new_draft).pack(side='left')

        self.protocol('WM_DELETE_WINDOW', self._on_close)

        # Toggle bar
        toggle_frame = tk.Frame(self, bg=DraftApp.BG)
        toggle_frame.pack(pady=(0, 10))

        tk.Label(toggle_frame, text='League:', bg=DraftApp.BG, fg=DraftApp.FG_DIM, font=DraftApp.FONT_STATUS).pack(side='left', padx=(0, 4))
        self.league_var = tk.StringVar(value=league)
        league_btn = tk.Label(toggle_frame, textvariable=self.league_var, bg=DraftApp.ACCENT, fg=DraftApp.FG,
                            font=DraftApp.FONT_STATUS, padx=8, pady=3, cursor='hand2')
        league_btn.pack(side='left', padx=(0, 16))
        league_btn.bind('<Button-1>', lambda e: self.league_var.set(
            'Smithfield' if self.league_var.get() == 'Fox Run' else 'Fox Run'))

        tk.Label(toggle_frame, text='Draft Type:', bg=DraftApp.BG, fg=DraftApp.FG_DIM, font=DraftApp.FONT_STATUS).pack(side='left', padx=(0, 4))
        self.draft_type_var = tk.StringVar(value=draft_type)
        draft_btn = tk.Label(toggle_frame, textvariable=self.draft_type_var, bg=DraftApp.ACCENT, fg=DraftApp.FG,
                            font=DraftApp.FONT_STATUS, padx=8, pady=3, cursor='hand2')
        draft_btn.pack(side='left')
        draft_btn.bind('<Button-1>', lambda e: self.draft_type_var.set(
            'all select' if self.draft_type_var.get() == 'mock draft' else 'mock draft'))

        tk.Label(toggle_frame, text='AI Agent:', bg=DraftApp.BG, fg=DraftApp.FG_DIM,
                font=DraftApp.FONT_STATUS).pack(side='left', padx=(0, 4))
        self.ai_var = tk.StringVar(value='AI Off')
        ai_btn = tk.Label(toggle_frame, textvariable=self.ai_var, bg=DraftApp.ACCENT, fg=DraftApp.FG,
                        font=DraftApp.FONT_STATUS, padx=8, pady=3, cursor='hand2')
        ai_btn.pack(side='left', padx=(0, 16))
        ai_btn.bind('<Button-1>', lambda e: self.ai_var.set(
            'AI Off' if self.ai_var.get() == 'AI On' else 'AI On'))


    def _on_close(self):
        sys.exit(0)


    def _on_double_click(self, event):
        self._resolve_selection()

    def _resume_selected(self):
        self._resolve_selection()


    def _resolve_selection(self):
        item = self._tree.focus()
        if not item:
            return
        idx = self._tree.index(item)
        self.selected_path = self._files[idx]
        self._tree.unbind('<Double-1>')
        self.after(10, self.destroy)   # defer destroy so the event fully unwinds first


    def _new_draft(self):
        self.selected_path = None
        self.destroy()


class DraftApp(tk.Tk):
    COLS_BASE = ['NAME', 'OVR_RK', 'POS', 'TEAM', 'PROJ_AVG', 'PRJ_PPR', 'L_ISHELP', 'L_NHELP', 'L_OUT', 'PRJ_OUT', 'INJ_RISK', 'OL_TIER']
    COLS_SIM  = ['NAME', 'OVR_RK', 'B_NEXT', 'POS', 'TEAM', 'PROJ_AVG', 'PRJ_PPR', 'L_ISHELP', 'L_NHELP', 'L_OUT', 'PRJ_OUT', 'INJ_RISK', 'OL_TIER']
    COL_WIDTHS = {'NAME': 180, 'OVR_RK': 70, 'B_NEXT': 70, 'POS': 55, 'TEAM': 60, 'PROJ_AVG': 78, 'L_ISHELP': 72, 'L_NHELP': 72, 'L_OUT': 60, 'OL_TIER': 65, 'INJ_RISK': 72, 'PRJ_OUT': 70, 'PRJ_PPR': 70}
    TEAM_COLS = ['POS', 'PLAYER']
    DRAFT_COLS = ['PICK', 'OWNER', 'POS', 'PLAYER']
 
    BG = '#1a1a2e'
    PANEL = '#16213e'
    ACCENT = '#0f3460'
    HIGHLIGHT = '#e94560'
    FG = '#eaeaea'
    FG_DIM = '#8888aa'
    FONT_MAIN = ('Consolas', 11)
    FONT_HEAD = ('Consolas', 11, 'bold')
    FONT_TITLE = ('Consolas', 14, 'bold')
    FONT_STATUS = ('Consolas', 10)

    def __init__(self, bridge: DraftBridge, league: str, user: str, draft_type: str, simulation: bool):
        super().__init__()
        self.bridge = bridge
        self.league = league
        self.user = user
        self.draft_type = draft_type
        self.simulation = simulation

        self.title(f'{league} Draft')
        self.configure(bg=self.BG)
        self.resizable(True, True)

        self._my_team_rows: list[tuple[str,str]] = []
        self._awaiting_input = False
        self._owner_teams: dict[str, list[tuple[str, str]]] = {}
        self._active_pos_filter: str | None = None
        self._active_search_filter: str | None = None

        self._build_style()
        self._build_layout()
        self._poll_queue()


    def _build_style(self):
        s = ttk.Style(self)
        s.theme_use('clam')

        s.configure('Draft.Treeview', background=self.PANEL, foreground=self.FG, fieldbackground=self.PANEL, rowheight=22, font=self.FONT_MAIN, borderwidth=0)
        s.configure('Draft.Treeview.Heading', background=self.ACCENT, foreground=self.FG, font=self.FONT_HEAD, relief='flat')
        s.map('Draft.Treeview', background=[('selected', self.HIGHLIGHT)], foreground=[('selected', '#ffffff')])

        # Team treeview (slightly narrower font)
        s.configure('Team.Treeview', background=self.PANEL, foreground=self.FG, fieldbackground=self.PANEL, rowheight=20, font=('Consolas', 10), borderwidth=0)
        s.configure('Team.Treeview.Heading', background=self.ACCENT, foreground=self.FG, font=('Consolas', 10, 'bold'), relief='flat')

        # Entry / Button
        s.configure('Pick.TEntry', fieldbackground=self.ACCENT, foreground=self.FG, insertcolor=self.FG, font=self.FONT_MAIN)
        s.configure('Pick.TButton', background=self.HIGHLIGHT, foreground='#ffffff', font=self.FONT_HEAD, relief='flat', padding=(8, 4))
        s.map('Pick.TButton', background=[('active', '#c73652'), ('disabled', '#555566')])

        s.configure('Mode.TButton', background=self.ACCENT, foreground=self.FG, font=('Consolas', 10), relief='flat', padding=(6, 3))
        s.map('Mode.TButton', background=[('active', self.HIGHLIGHT)])

        s.configure('Undo.TButton', background=self.ACCENT, foreground=self.FG, font=self.FONT_HEAD, relief='flat', padding=(8, 4))
        s.map('Undo.TButton', background=[('active', '#1a4a8a'), ('disabled', '#555566')])


    def _build_layout(self):
        top = tk.Frame(self, bg=self.BG, pady=6)
        top.pack(fill='x', padx=12)

        tk.Label(top, text='⬡  FANTASY DRAFT', bg=self.BG, fg=self.HIGHLIGHT, font=self.FONT_TITLE).pack(side='left')

        self._mode_var = tk.StringVar(value=self.draft_type)
        self._mode_btn = ttk.Button(top, textvariable=self._mode_var, style='Mode.TButton', command=self._toggle_mode)
        self._mode_btn.pack(side='right', padx=4)
        tk.Label(top, text='Mode:', bg=self.BG, fg=self.FG_DIM, font=self.FONT_STATUS).pack(side='right')

        # Status bar
        self._status_var = tk.StringVar(value='Initializing draft...')
        tk.Label(self, textvariable=self._status_var, bg=self.ACCENT, fg=self.FG, font=self.FONT_STATUS, anchor='w', padx=8, pady=3).pack(fill='x', padx=0)

        self._build_agent_panel()

        # Main body: left = next-up table, right = my team
        body = tk.Frame(self, bg=self.BG)
        body.pack(fill='both', expand=True, padx=12, pady=6)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_next_up_panel(body)
        self._build_team_panel(body)

        # Pick input (full width below body)
        self._build_pick_panel()


    def _build_next_up_panel(self, parent):
        frame = tk.Frame(parent, bg=self.PANEL, bd=1, relief='flat')
        frame.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
 
        # Tab bar
        tab_bar = tk.Frame(frame, bg=self.PANEL)
        tab_bar.grid(row=0, column=0, columnspan=2, sticky='ew')

        self._pos_tab_buttons: dict[str | None, tk.Label] = {}
        tab_positions = [None] + POS_LIST + ['FLEX']

        for pos in tab_positions:
            label = 'ALL' if pos is None else pos
            btn = tk.Label(
                tab_bar, text=label, bg=self.ACCENT, fg=self.FG_DIM,
                font=self.FONT_STATUS, padx=8, pady=3, cursor='hand2'
            )
            btn.pack(side='left', padx=(0, 1))
            btn.bind('<Button-1>', lambda e, p=pos: self._set_pos_filter(p))
            self._pos_tab_buttons[pos] = btn

        # Highlight the default (ALL) tab
        self._set_pos_filter(None)

        cols = self.COLS_SIM if self.simulation else self.COLS_BASE
        self._next_tree = ttk.Treeview(frame, columns=cols, show='headings', style='Draft.Treeview', selectmode='browse')
        self._apply_columns(self._next_tree, cols)
 
        vsb = ttk.Scrollbar(frame, orient='vertical', command=self._next_tree.yview)
        self._next_tree.configure(yscrollcommand=vsb.set)
        self._next_tree.grid(row=1, column=0, sticky='nsew')
        vsb.grid(row=1, column=1, sticky='ns')
 
        # Double-click to auto-fill pick entry
        self._next_tree.bind('<ButtonRelease-1>', self._on_row_click)

        # Sorting state: (column, ascending)
        self._sort_state: tuple[str, bool] = ('OVR_RK', True)

        # Injury tooltip
        self._injury_map: dict[str, str] = {}   # player name → note
        self._tooltip = _Tooltip(self._next_tree)
        self._next_tree.bind('<Motion>',    self._on_tree_motion)
        self._next_tree.bind('<Leave>',     lambda e: self._tooltip.hide())

        # Make each heading clickable for sorting
        cols = self.COLS_SIM if self.simulation else self.COLS_BASE
        for col in cols:
            self._next_tree.heading(col, text=col,
                                    command=lambda c=col: self._sort_by(c))
            

    def _build_team_panel(self, parent):
        frame = tk.Frame(parent, bg=self.PANEL, bd=1, relief='flat')
        frame.grid(row=0, column=1, sticky='nsew')
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)
 
        tab_bar = tk.Frame(frame, bg=self.PANEL)
        tab_bar.grid(row=0, column=0, columnspan=2, sticky='ew')

        self._right_panel_tab = tk.StringVar(value='team')

        self._team_tab_btn = tk.Label(tab_bar, text='MY TEAM', bg=self.HIGHLIGHT, fg='#ffffff',
                                    font=self.FONT_STATUS, padx=8, pady=3, cursor='hand2')
        self._team_tab_btn.pack(side='left', padx=(0, 1))
        self._team_tab_btn.bind('<Button-1>', lambda e: self._set_right_panel('team'))

        self._board_tab_btn = tk.Label(tab_bar, text='DRAFTBOARD', bg=self.ACCENT, fg=self.FG_DIM,
                                        font=self.FONT_STATUS, padx=8, pady=3, cursor='hand2')
        self._board_tab_btn.pack(side='left', padx=(0, 1))
        self._board_tab_btn.bind('<Button-1>', lambda e: self._set_right_panel('board'))

        self._team_label_var = tk.StringVar(value='TEAM')
        tk.Label(frame, textvariable=self._team_label_var,
                bg=self.PANEL, fg=self.FG_DIM, font=self.FONT_STATUS,
                anchor='w', padx=6, pady=2).grid(row=1, column=0, columnspan=2, sticky='ew')
        

        # Team treeview
        self._team_frame = tk.Frame(frame, bg=self.PANEL)
        self._team_frame.grid(row=2, column=0, columnspan=2, sticky='nsew')
        self._team_frame.rowconfigure(0, weight=1)
        self._team_frame.columnconfigure(0, weight=1)

        self._team_tree = ttk.Treeview(self._team_frame, columns=self.TEAM_COLS, show='headings', style='Team.Treeview', selectmode='none')
        for col in self.TEAM_COLS:
            w = 55 if col == 'POS' else 140
            self._team_tree.heading(col, text=col)
            self._team_tree.column(col, width=w, anchor='w', stretch=False)
        vsb2 = ttk.Scrollbar(self._team_frame, orient='vertical', command=self._team_tree.yview)
        self._team_tree.configure(yscrollcommand=vsb2.set)
        self._team_tree.grid(row=0, column=0, sticky='nsew')
        vsb2.grid(row=0, column=1, sticky='ns')

        # Draftboard treeview
        self._board_frame = tk.Frame(frame, bg=self.PANEL)
        self._board_frame.rowconfigure(0, weight=1)
        self._board_frame.columnconfigure(0, weight=1)

        self._board_tree = ttk.Treeview(self._board_frame, columns=self.DRAFT_COLS, show='headings', style='Team.Treeview', selectmode='none')
        for col in self.DRAFT_COLS:
            w = 45 if col == 'PICK' else 55 if col == 'POS' else 120
            self._board_tree.heading(col, text=col)
            self._board_tree.column(col, width=w, anchor='w', stretch=(col == 'PLAYER'))
        vsb3 = ttk.Scrollbar(self._board_frame, orient='vertical', command=self._board_tree.yview)
        self._board_tree.configure(yscrollcommand=vsb3.set)
        self._board_tree.grid(row=0, column=0, sticky='nsew')
        vsb3.grid(row=0, column=1, sticky='ns')

 
    def _build_pick_panel(self):
        outer = tk.Frame(self, bg=self.BG, pady=8)
        outer.pack(fill='x', padx=12, pady=(0, 12))

        inner = tk.Frame(outer, bg=self.BG)
        inner.pack(anchor='center')

        tk.Label(inner, text='SEARCH:', bg=self.BG, fg=self.FG, font=self.FONT_HEAD).pack(side='left', padx=(0, 6))

        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(inner, textvariable=self._search_var, style='Pick.TEntry', width=28)
        search_entry.pack(side='left', padx=(0, 8))
        search_entry.bind('<Return>', lambda _: self._apply_search())

        ttk.Button(inner, text='Search', style='Mode.TButton', width=12, command=self._apply_search).pack(side='left', padx=(0, 4))
        ttk.Button(inner, text='Clear', style='Mode.TButton', width=12, command=self._clear_search).pack(side='left', padx=(0, 24))

        tk.Label(inner, text='PICK:', bg=self.BG, fg=self.FG, font=self.FONT_HEAD).pack(side='left', padx=(0, 6))
 
        self._pick_var = tk.StringVar()
        self._pick_entry = ttk.Entry(inner, textvariable=self._pick_var, style='Pick.TEntry', width=28)
        self._pick_entry.pack(side='left', padx=(0, 8))
        self._pick_entry.bind('<Return>', lambda _: self._submit_pick())
        self._pick_entry.config(state='disabled')
 
        self._pick_btn = ttk.Button(inner, text='Draft Player', style='Pick.TButton', width=12, command=self._submit_pick)
        self._pick_btn.pack(side='left')
        self._pick_btn.config(state='disabled')

        self._undo_btn = ttk.Button(inner, text='↩ Undo', style='Undo.TButton', width=12, command=self._submit_undo)
        self._undo_btn.pack(side='left', padx=(8, 0))
        self._undo_btn.config(state='disabled')
 
        self._pick_feedback = tk.Label(inner, text='', bg=self.BG, fg=self.HIGHLIGHT, font=self.FONT_STATUS)
        self._pick_feedback.pack(side='left', padx=12)


    def _build_agent_panel(self):
        self._agent_frame = tk.Frame(self, bg=self.PANEL, pady=6)
        self._agent_frame.pack(fill='x', padx=12, pady=(0, 4))

        tk.Label(self._agent_frame, text='AGENT RECOMMENDATIONS',
                bg=self.PANEL, fg=self.HIGHLIGHT, font=self.FONT_HEAD,
                anchor='w', padx=8).pack(fill='x')

        btn_row = tk.Frame(self._agent_frame, bg=self.PANEL)
        btn_row.pack(fill='x', padx=8, pady=(4, 2))

        # Three agent pick buttons
        self._agent_btns = {}
        for label in ('Logical', 'Probabilistic', 'Gemini'):
            col_frame = tk.Frame(btn_row, bg=self.PANEL)
            col_frame.pack(side='left', padx=(0, 12))

            tk.Label(col_frame, text=label, bg=self.PANEL, fg=self.FG_DIM,
                    font=self.FONT_STATUS).pack(anchor='w')

            btn = tk.Button(col_frame, text='—', bg=self.ACCENT, fg=self.FG,
                            font=self.FONT_STATUS, relief='flat', padx=8, pady=3,
                            state='disabled', cursor='hand2',
                            command=lambda l=label: self._agent_btn_click(l))
            btn.pack(anchor='w')
            self._agent_btns[label] = btn

        # gemini reasoning
        self._agent_reasoning_var = tk.StringVar(value='')
        tk.Label(self._agent_frame, textvariable=self._agent_reasoning_var,
                bg=self.PANEL, fg=self.FG_DIM, font=self.FONT_STATUS,
                anchor='w', padx=8, wraplength=900, justify='left').pack(fill='x', pady=(2, 0))



    def _show_agent_picks(self, payload: dict):
        mapping = {
            'Logical': payload.get('logical'),
            'Probabilistic': payload.get('probabilistic'),
            'Gemini': payload.get('gemini'),
        }
        for label, name in mapping.items():
            btn = self._agent_btns[label]
            if name:
                btn.config(text=name, state='normal')
            else:
                btn.config(text='—', state='disabled')

        self._agent_reasoning_var.set(payload.get('reasoning') or '')
        
        # Clear buttons when pick input is disabled
        self._agent_picks_cache = mapping


    def _agent_btn_click(self, label: str):
        if not self._awaiting_input:
            return
        name = self._agent_picks_cache.get(label)
        if name:
            self._pick_var.set(name)
            self._pick_entry.focus_set()


    def _submit_undo(self):
        if self._awaiting_input:
            self._disable_pick_input()
        self.bridge.pending_pick = None
        self.bridge.pending_undo = True
        self.bridge.pick_event.set()
        self._pick_feedback.config(text='Undoing last pick...')

 
    def _apply_columns(self, tree, cols):
        tree['columns'] = cols
        for col in cols:
            w = self.COL_WIDTHS.get(col, 80)
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor='w', stretch=(col == 'NAME'))
 
 
    def _poll_queue(self):
        try:
            while True:
                cmd, payload = self.bridge.ui_queue.get_nowait()
                if cmd == 'status':
                    self._status_var.set(payload)
                elif cmd == 'next_up':
                    self._refresh_next_up(payload)
                elif cmd == 'my_pick':
                    self._enable_pick_input(payload)
                elif cmd == 'team_pick':
                    self._add_team_pick(payload)
                elif cmd == 'done':
                    self._on_draft_done(payload)
                elif cmd == 'columns':
                    self._apply_columns(self._next_tree, payload)
                elif cmd == 'load_team':
                    owner, picks = payload   # picks is list[tuple[str, str]]
                    self._team_label_var.set(f'TEAM  ({owner})')
                    self._team_tree.delete(*self._team_tree.get_children())
                    for pos, name in picks:
                        self._team_tree.insert('', 'end', values=(pos, name))

                elif cmd == 'undo_enable':
                    self._undo_btn.config(state='normal')
                elif cmd == 'undo_disable':
                    self._undo_btn.config(state='disabled')
                elif cmd == 'undo_team':
                    owner, picks = payload
                    self._owner_teams[owner] = picks
                    self._team_label_var.set(f'TEAM  ({owner})')
                    self._team_tree.delete(*self._team_tree.get_children())
                    for pos, name in picks:
                        self._team_tree.insert('', 'end', values=(pos, name))

                elif cmd == 'agent_picks':
                    self._show_agent_picks(payload)
                                
        except q_module.Empty:
            pass
        self.after(80, self._poll_queue)
 
 
    def _refresh_next_up(self, next_up_dict: dict) -> None:
        self._last_next_up_dict = next_up_dict
        self._render_next_up(next_up_dict)


    def _render_next_up(self, next_up_dict: dict) -> None:
        self._next_tree.delete(*self._next_tree.get_children())
        cols = self.COLS_SIM if self.simulation else self.COLS_BASE
        n_sims = None
        try:
            from globals import N_SIMULATIONS
            n_sims = N_SIMULATIONS
        except Exception:
            pass

        active = self._active_pos_filter
        col, asc = self._sort_state

        # Filter first, then sort
        filtered = []
        for player_name, info in next_up_dict.items():
            pos = info.get('POS', '')
            if active is not None:
                if active == 'FLEX':
                    if pos not in FLEX_POSITIONS:
                        continue
                elif pos != active:
                    continue
            if self._active_search_filter is not None:
                if self._active_search_filter not in player_name.upper():
                    continue
            filtered.append((player_name, info))

        filtered.sort(key=lambda item: self._sort_key(item, col), reverse=not asc)

        for player_name, info in filtered:
            # Cache injury note for tooltip
            inj = info.get('INJURY')
            if inj and str(inj).strip() and str(inj).lower() not in ('nan', 'none', ''):
                self._injury_map[player_name] = str(inj).strip()
            else:
                self._injury_map.pop(player_name, None)

            row = []
            for col in cols:
                if col == 'NAME':
                    val = player_name
                elif col == 'B_NEXT':
                    count = info.get('count', 0)
                    if n_sims and count > 0:
                        val = f"{round(count / n_sims * 100, 1)}%"
                    else:
                        val = 'N/A'
                else:
                    v = info.get(col)
                    if v is None:
                        val = 'N/A'
                    elif isinstance(v, float):
                        if col in ('L_ISHELP', 'L_NHELP'):
                            val = f"{round(v * 100, 1)}%"
                        else:
                            val = str(round(v, 1))
                    else:
                        val = str(v)

                if 'NAN' in val.upper():
                    val = 'N/A'

                row.append(val)
            self._next_tree.insert('', 'end', values=row)
 
 
    def _set_right_panel(self, tab: str) -> None:
        self._right_panel_tab.set(tab)
        if tab == 'team':
            self._board_frame.grid_remove()
            self._team_frame.grid(row=2, column=0, columnspan=2, sticky='nsew')
            self._team_tab_btn.config(bg=self.HIGHLIGHT, fg='#ffffff')
            self._board_tab_btn.config(bg=self.ACCENT, fg=self.FG_DIM)
        else:
            self._team_frame.grid_remove()
            self._board_frame.grid(row=2, column=0, columnspan=2, sticky='nsew')
            self._board_tab_btn.config(bg=self.HIGHLIGHT, fg='#ffffff')
            self._team_tab_btn.config(bg=self.ACCENT, fg=self.FG_DIM)


    def _add_team_pick(self, payload: tuple[str, str, str]):
        owner, pos, name = payload
        if owner not in self._owner_teams:
            self._owner_teams[owner] = []
        self._owner_teams[owner].append((pos, name))

        current_shown = self._team_label_var.get()
        if owner in current_shown:
            self._team_tree.insert('', 'end', values=(pos, name))

        # Always append to draftboard regardless of whose pick it is
        pick_num = sum(len(v) for v in self._owner_teams.values())
        self._board_tree.insert('', 'end', values=(pick_num, owner, pos, name))
        # Auto-scroll to latest pick
        children = self._board_tree.get_children()
        if children:
            self._board_tree.see(children[-1])
 
 
    def _enable_pick_input(self, prompt: str):
        self._awaiting_input = True
        self._status_var.set(prompt)
        self._pick_var.set('')
        self._pick_feedback.config(text='')
        self._pick_entry.config(state='normal')
        self._pick_btn.config(state='normal')
        self._pick_entry.focus_set()

 
    def _disable_pick_input(self):
        self._awaiting_input = False
        self._pick_entry.config(state='disabled')
        self._pick_btn.config(state='disabled')
        # Disable agent buttons until next pick
        for btn in self._agent_btns.values():
            btn.config(state='disabled')

 
    def _submit_pick(self):
        if not self._awaiting_input:
            return
        name = self._pick_var.get().strip()
        if not name:
            self._pick_feedback.config(text='Enter a player name.')
            return
        
        # Pass the raw string to the draft thread
        self.bridge.pending_pick = name
        self.bridge.pick_event.set()
        self._disable_pick_input()
        self._pick_feedback.config(text=f'Submitting "{name}"...')
 
    def _on_row_click(self, event):
        item = self._next_tree.focus()
        if not item:
            return
        values = self._next_tree.item(item, 'values')
        if values:
            self._pick_var.set(values[0])   # NAME is always first col
 
 
    def _toggle_mode(self):
        current = self._mode_var.get()
        new = 'all select' if current == 'mock draft' else 'mock draft'
        self._mode_var.set(new)
        self.draft_type = new
        self.bridge.ui_queue.put(('status', f'Mode switched to "{new}" — takes effect next pick.'))
 
 
    def _on_draft_done(self, results: str):
        self._status_var.set('Draft complete!')
        self._disable_pick_input()
        win = tk.Toplevel(self)
        win.title('Draft Complete')
        win.configure(bg=self.BG)
        win.resizable(True, True)

        tk.Label(win, text='Draft Results', bg=self.BG, fg=self.HIGHLIGHT, font=self.FONT_TITLE, pady=8).pack()

        frame = tk.Frame(win, bg=self.PANEL)
        frame.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        text = tk.Text(frame, bg=self.PANEL, fg=self.FG, font=self.FONT_MAIN, relief='flat', wrap='none')
        vsb = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=vsb.set)
        text.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')

        text.insert('1.0', results)
        text.config(state='disabled')

        tk.Button(win, text='Close', bg=self.ACCENT, fg=self.FG, font=self.FONT_HEAD,
                relief='flat', padx=10, pady=4, command=win.destroy).pack(pady=10)


    def _set_pos_filter(self, pos: str | None) -> None:
        self._active_pos_filter = pos
        for p, btn in self._pos_tab_buttons.items():
            if p == pos:
                btn.config(bg=self.HIGHLIGHT, fg='#ffffff')
            else:
                btn.config(bg=self.ACCENT, fg=self.FG_DIM)
        # Re-render the current table with the new filter applied
        if hasattr(self, '_last_next_up_dict'):
            self._render_next_up(self._last_next_up_dict)


    def _apply_search(self):
        query = self._search_var.get().strip().upper()
        self._active_search_filter = query if query else None
        if hasattr(self, '_last_next_up_dict'):
            self._render_next_up(self._last_next_up_dict)


    def _clear_search(self):
        self._search_var.set('')
        self._active_search_filter = None
        if hasattr(self, '_last_next_up_dict'):
            self._render_next_up(self._last_next_up_dict)


    def _sort_by(self, col: str) -> None:
        """Toggle sort direction on col; re-render from the cached dict."""
        _, asc = self._sort_state
        # Clicking the same column flips direction; new column resets to asc
        new_asc = not asc if col == self._sort_state[0] else True
        self._sort_state = (col, new_asc)

        # Update heading arrows
        cols = self.COLS_SIM if self.simulation else self.COLS_BASE
        for c in cols:
            arrow = ''
            if c == col:
                arrow = ' ▲' if new_asc else ' ▼'
            self._next_tree.heading(c, text=c + arrow,
                                    command=lambda _c=c: self._sort_by(_c))

        if hasattr(self, '_last_next_up_dict'):
            self._render_next_up(self._last_next_up_dict)


    def _sort_key(self, item: tuple[str, dict], col: str):
        """Return a sort key for a (name, info) pair given column name."""
        name, info = item
        if col == 'NAME':
            return name.upper()
        if col == 'B_NEXT':
            return info.get('count', 0)           # raw count, not formatted %

        raw = info.get(col)
        if raw is None:
            return float('inf')                   # N/A goes to the end
        if isinstance(raw, (int, float)):
            return raw
        # Try to parse strings like "12.3" or "45.6%"
        try:
            return float(str(raw).replace('%', ''))
        except ValueError:
            return str(raw).upper()


    def _on_tree_motion(self, event: tk.Event) -> None:
        """Show tooltip when hovering over a NAME cell of a player with an injury note."""
        item = self._next_tree.identify_row(event.y)
        col  = self._next_tree.identify_column(event.x)
        if not item or col != '#1':             # #1 = first visible column = NAME
            self._tooltip.hide()
            return

        name = self._next_tree.item(item, 'values')
        if not name:
            self._tooltip.hide()
            return
        name = name[0]                          # first value is always NAME

        note = self._injury_map.get(name)
        if note and str(note).strip() and str(note).lower() not in ('nan', 'none', ''):
            self._tooltip.show(f'🩹 {note}', event.x_root, event.y_root)
        else:
            self._tooltip.hide()


class _Tooltip:
    """Lightweight Toplevel tooltip that follows the mouse."""
    def __init__(self, widget: tk.Widget):
        self._widget = widget
        self._tip: tk.Toplevel | None = None

    def show(self, text: str, x: int, y: int):
        self.hide()
        self._tip = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)          # no title bar / borders
        tw.wm_geometry(f'+{x + 16}+{y + 8}')
        tk.Label(tw, text=text, justify='left',
                 background='#ffffcc', foreground='#222222',
                 relief='solid', borderwidth=1,
                 font=('Consolas', 10), wraplength=320,
                 padx=6, pady=4).pack()

    def hide(self):
        if self._tip:
            self._tip.destroy()
            self._tip = None
