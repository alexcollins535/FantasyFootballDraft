import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue as q_module
import random
import pickle
import os 
import sys
from datetime import datetime

from globals import SEED, POS_LIST, FLEX_POSITIONS
from draft_functionality import initialize_draft, run_simulation
from infrastructure import DraftBlackboard


class DraftBridge:
    def __init__(self):
        self.pick_event = threading.Event()
        self.pending_pick: str | None = None
        self.ui_queue: q_module.Queue = q_module.Queue()
        self.pending_undo: bool = False


class LoadScreen(tk.Tk):
    def __init__(self, saved_dir: str, league: str, draft_type: str):
        super().__init__()
        self.title('Fantasy Draft — Load')
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

            row = []
            for col in cols:
                if col == 'NAME':
                    val = player_name
                elif col == 'B_NEXT':
                    count = info.get('count', 0)
                    val = f"{round(count / n_sims * 100, 1)}%" if n_sims else str(count)
                elif col not in info:
                    val = 'N/A'
                else:
                    v = info[col]
                    if isinstance(v, float):
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


class DraftWorker:
    def __init__(self, bridge: DraftBridge, app: DraftApp, league: str, user: str, draft_type: str, simulation: bool):
        self.bridge = bridge
        self.app = app
        self.league = league
        self.user = user
        self.draft_type = draft_type
        self.simulation = simulation

        self._user_pick_count = 0


    def push(self, cmd, payload=None):
        self.bridge.ui_queue.put((cmd, payload))


    def _show_next_up(self, blackboard: DraftBlackboard):
        # Replacement for print_next_up_players in UI workflow
        if self.simulation and blackboard.current_pick_owner == self.user:
            next_up_dict = run_simulation(blackboard)
        else:
            next_up_dict = {}
            for player in blackboard.next_up_queue.heap:
                next_up_dict[player.name] = {'POS': player.pos, 'TEAM': player.team, 'OVR_RK': player.ovr_rk}
                if player.name in blackboard.additional_data_dict:
                    d = blackboard.additional_data_dict[player.name]
                    next_up_dict[player.name].update({
                        'PROJ_AVG': d.get('ProjAvg'),
                        'L_OUT': d.get('OutLast'),
                        'L_ISHELP': d.get('IsHelp'),
                        'L_NHELP': d.get('NeedHelp'),
                        'OL_TIER': d.get('OLTier'),
                        'INJ_RISK': d.get('InjRisk'),
                        'PRJ_OUT': d.get('ProjOut'),
                        'PRJ_PPR': d.get('ProjPPR')
                    })
        self.push('next_up', next_up_dict)


    def _ui_select_pick(self, blackboard: DraftBlackboard):
        # Replacement for make_select_pick in UI workflow
        owner = blackboard.current_pick_owner
        rd = blackboard.current_round
        pick = blackboard.current_pick_in_round

        while True:
            self.bridge.pick_event.clear()
            self.push('load_team', (owner, self.app._owner_teams.get(owner, [])))
            self.push('my_pick', f"{rd}.{pick} Draft selection for {owner}: ")
            self.bridge.pick_event.wait()

            if self.bridge.pending_undo:
                self.bridge.pending_undo = False
                return False

            raw = (self.bridge.pending_pick or '').strip()
            queue = blackboard.next_up_queue

            if raw in queue.name_to_player_map:
                player_obj = queue.name_to_player_map[raw]
            else:
                upper = raw.upper()
                matches = [p.name for p in queue.heap if any(part in upper for part in p.name.upper().split()[:2])]
                if len(matches) == 1:
                    player_obj = queue.name_to_player_map[matches[0]]
                elif matches:
                    self.push('status', f'Multiple matches for "{raw}": {", ".join(matches[:5])}. Enter full name.')
                    continue
                else:
                    self.push('status', f'No matches found for "{raw}".')
                    continue

            blackboard.draft_player(player_obj, print_picks=False)
            if blackboard.in_progress:
                blackboard.update_odds()
            self.push('team_pick', (owner, player_obj.pos, player_obj.name))
            if owner == self.user:
                self._user_pick_count += 1
                self.push('undo_enable')
            self.push('status', f'Drafted: {player_obj.name}, {player_obj.pos}')
            return True


    def run(self, load_state: DraftBlackboard=None):
        if load_state is None:
            blackboard = initialize_draft(self.league, self.draft_type)
        else:
            blackboard = load_state
            self._restore_ui_from_state(blackboard)

        self.push('status', f'Draft started for {self.league}')
 
        while blackboard.in_progress:
            # Keeper pick 
            keeper_drafted = False
            if blackboard.keepers is not None:
                owner = blackboard.current_pick_owner
                rd = blackboard.current_round
                if blackboard.keepers[owner]['ROUND'] == rd:
                    player_obj = blackboard.keepers[owner]['PLAYER_OBJ']
                    blackboard.draft_player(player_obj, print_picks=False, keeper_pick=True)
                    self.push('team_pick', (owner, player_obj.pos, player_obj.name))
                    self.push('status', f'Keeper: {player_obj.name} ({player_obj.pos}) to {owner}')
                    if blackboard.in_progress:
                        blackboard.update_odds()
                    keeper_drafted = True
 
            if keeper_drafted:
                continue
 
            owner = blackboard.current_pick_owner
            is_user_pick = (owner == self.user)
            current_type = self.app.draft_type   # may have been toggled
 
            # User pick
            if current_type == 'all select' or (current_type == 'mock draft' and is_user_pick):
                if current_type == 'all select' or blackboard.current_round != blackboard.last_round:
                    self._show_next_up(blackboard)
                picked = self._ui_select_pick(blackboard)
                if not picked:
                    # Undo: rewind to previous user pick, rebuild team panel
                    blackboard.go_back_to_last_user_pick(current_type)
                    blackboard.update_odds()
                    self._user_pick_count -= 1
                    if self._user_pick_count == 0:
                        self.push('undo_disable')
                    updated_picks = [(blackboard.player_data_dict[p]['POS'], p) for p in blackboard.players_drafted_by_owner[self.user]]
                    self.push('undo_team', (self.user, updated_picks))
                    self._show_next_up(blackboard)
                    continue

                self._autosave(blackboard)
            
            # Random pick 
            else:
                blackboard.make_random_pick(print_picks=False)
                drafted = blackboard.players_drafted_by_owner['LEAGUE'][-1]
                # Already drafted needs handling for previous was last pick in round
                if blackboard.current_pick_in_round == 1:
                    last_pick = 12
                    last_pick_rd = blackboard.current_round - 1
                else:
                    last_pick = blackboard.current_pick_in_round - 1
                    last_pick_rd = blackboard.current_round

                self.push('team_pick', (owner, drafted.pos, drafted.name))
                self.push('status', f'Pick {last_pick_rd}.{last_pick}: {owner} drafts {drafted.name}, {drafted.pos}')
                if blackboard.in_progress:
                    blackboard.update_odds()
 
        # Draft over
        results_lines = []
        for owner, players in blackboard.players_drafted_by_owner.items():
            if owner == 'LEAGUE':
                continue
            pos_map: dict[str, list] = {}
            for p in dict.fromkeys(players):
                pos = blackboard.player_data_dict[p]['POS']
                pos_map.setdefault(pos, []).append(p)
            results_lines.append(f'\n{owner}')
            for pos in POS_LIST:
                if pos in pos_map:
                    results_lines.append(f'  {pos}: {", ".join(pos_map[pos])}')
 
        self.push('done', '\n'.join(results_lines))


    def _autosave(self, blackboard: DraftBlackboard) -> None:
        date_str = datetime.now().strftime('%Y%m%d')
        path = os.path.join('saved_draft_states', f'{self.league}_{date_str}_autosave.pkl')
        os.makedirs('saved_draft_states', exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(blackboard, f)


    def _restore_ui_from_state(self, blackboard: DraftBlackboard) -> None:
        for action in blackboard.action_log:
            if not action.startswith('Pick'):
                continue
            try:
                after_colon = action.split(': ', 1)[1]
                owner, rest = after_colon.split(' drafts ', 1)
                name, pos = rest.rsplit(', ', 1)
            except ValueError:
                continue

            self.push('team_pick', (owner, pos, name))  # _add_team_pick handles _owner_teams

            if owner == self.user:
                self._user_pick_count += 1

        if self._user_pick_count > 0:
            self.push('undo_enable')


def launch_ui(league: str, user: str, draft_type: str='mock draft', simulation: bool=True):
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
    app = DraftApp(bridge, league=league, user=user, draft_type=draft_type, simulation=simulation)

    worker = DraftWorker(bridge, app, league=league, user=user, draft_type=draft_type, simulation=simulation)

    thread = threading.Thread(target=worker.run, args=(load_state,), daemon=True)
    thread.start()

    app.mainloop()



if __name__ == '__main__':
    random.seed(SEED)
    launch_ui(league='Fox Run', user='Alex', draft_type='all select', simulation=False)