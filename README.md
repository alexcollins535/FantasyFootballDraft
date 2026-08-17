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

Following data update, run preprocessing.py to create the reference JSON files.
Then decide on the functionality in main.py. Currently available:
* launch_ui() - the main functionality, choose either 'select all' as a conventional pick all draft or 'mock draft' to simulate non-user picks. The simulation arg is the choice to run 32 simulations of the picks before the next to determine players who are likely picked before next.
* run_draft_type() - runs the draft in terminal. Also allows 'random all' where no user picks are made.
* run_player_counts_by_round_in_simulation() - runs 25 full draft simulations and counts for each player, the number of times they were drafted in each round. Publishes data to csv.
* run_player_selection_by_pick() - runs 25 full draft simulations and records the picks in order for each draft. Publishes data for each league to csv.
