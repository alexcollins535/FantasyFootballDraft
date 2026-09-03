# FantasyFootballDraft
A Fantasy Football draft simulation model with an accompanying UI. 

## Setup
The FFL_Reference.xlsx file is used as the reference data file. 

Update over time:
* Update pos_rk using fantasypros.com positional PPR rankings, copy and paste the tables
* Update ovr_rk using fantasypros.com PPR rankings, copy and paste the table

Update with new league:
* past_draft_by_round is a manual update table, count of each position drafted across the league each round
* ct_draft_by_team is a manual update table, the average and standard deviation of the total for each position picked by a given team across all years
* my_stats is a manual update table, selected fields to be displayed when selecting a player (column changes requires an update of preprocessing.py, user_interface.py BASE_COLS, and infrastructure.py print in terminal method)
* globals.py contains the league names, owners, draft order, keeper picks

Note: if a league is named in main.py which is missing from any of the files, the code falls back to the default settings specified in the spreadsheet and globals.py 

## Functionality
The application is structured as a multi-layered AI system, implemented in LangGraph, built on top of a custom draft engine, combining deterministic modeling, probabilistic simulation, and LLM reasoning into a unified human-in-the-loop recommendation interface.

### Centralized Draft State
All components in the system operate on a central DraftState: a shared TypedDict that serves as the environment for the agents to act within throughout the draft. It carries the full draft board, pick history, keeper assignments, roster construction per team, pick order, and the outputs of each agent (logical pick, probabilistic pick, LLM pick and reasoning, and the user's final selection). The agent graph, simulation framework, and UI read from and write to this shared state.

### Draft Engine
The draft engine is responsible for mutating the draft state on behalf of simulated opponents. Its primary operations are updating the player selection odds as picks are made and executing simulated picks. The selection odds factor in the following:
* Player positional ranking by experts (average rank, standard deviation)
* Owner positional need (raw values which weight starters more heavily than backups)
* Owner total by position tendencies (example: player always drafts 2 QBs)
* League positional tendencies by round (example: league drafts an average of 8 RBs in round 1)
For player selection, first a position is randomly selected, weighted based on the factors mentioned above. Then a player from that position is randomly selected, based on expert consensus rankings for players at that position.

### Monte Carlo Simulation Framework
At draft time, the simulation framework runs 32 passes over the time frame up to the user's next pick to estimate player availability at the next pick to inform the current choice. For each player, it produces a likelihood that they will still be available at the next pick.

### Multi-Agent Recommendation System
Three recommendation agents run in parallel to produce relatively independent (there is naturally similar signal learned from past information in all three agents) recommendations:
* LogicalDraftAgent: A deterministic, rules-based agent that applies positional scarcity logic and roster construction heuristics, alongside personal player preferences to identify the optimal pick at each step.
* ProbabilisticDraftAgent: A deterministic, odds-based agent which factors in expert consensus rankings along with owner tendencies to produce the recommendation with the highest odds of being selected in the case of a random pick by the draft engine.
* Gemini Agent (gemini-2.5-flash): An LLM agent that reasons contextually over the current roster, draft history, and pick position. The available player pool is withheld to keep its signal independent from the probabilistic agent and avoid redundant recommendations.

### Multithreaded Architecture
The Tkinter UI and the LangGraph agent graph run on separate threads, bridged by two thread-safe queues. A background thread drives opponent picks and triggers agent runs; the UI thread polls for results and updates the display.
