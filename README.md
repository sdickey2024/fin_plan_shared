# Financal Planning

* provide tools to perform customized financial planning.
* generate a montecarlo analysis of outcomes
* allow various stages and ages of activity for example
  * retirement date
  * date children are done with daycare, which may be later
  * date children are done with expensive afterschool programs
    * for example, when school days last past 3pm (highschool?)
  * accounting for my current expenses to generate current and
  * estimated expenditures
  * accounting for wife's current and estimated expenses
* allow various simulations to be run, pre-defined

# Installation/Setup
* This a python based tool. Proper Python Install Is Required
## To Intsall And Setup
```
mkdir -p ~/python_venv
python3 -m venv ~/python_venv/fin_plan
source ~/python_venv/fin_plan/bin/activate
pip install pyfolio-reloaded quantstats matplotlib pandas jsonschema pydantic typer argparse plotly
```

* to exit:
```
(fin_plan)...$ deactivate
```

# Data Sources and Program Structure
This program is a little primitive at the moment. The json files are comprised of
a user "base" scenario stored in

```
data/firstname_lastname.json
```

And scenarios to be run.  Currently the scenarios are

```
user_data.json                         Generic Assumptions And Variability
user_data_stress.json                  Specific Stressors Added
user_data_ltc.json                     Massive Long Term Care Costs
user_data_scenario_1_market_crash.json Really Tough Market Crash
user_data_scenario_2_market_crash.json Really Tough Market Crash 2
user_data_worst_crashes.json           10 Years after Historic Crashes
```

Any scenario can be written as you see fit.

The general structure of a user json file is at a high level

```
<personal data, retirement age, length of simulation>
<current income>
<current expenses
<breakdown, can be anything you want to track>>
<portfolio
<breakdown, taxable, non-taxable, savings, brokerage>>
```

The general structure of a scenario json file is

```
<description>
<life events
<event
<updated income>
<updated assumptions>
<updated expenses>>
<base assumptions
<expected return>
<variance>
<inflation>>
```

# Limitations
* There are many!  Sorry, lots of work needs to be done here

** The life events are by DATE rather than by year from start of simulation. This
is totally stupid because next year I'll have to change all the dates.

** Life events need to be in order

** The names of various sections really need to be as written in the examples

*** e.g. "updated_assumptions" and "updated_expenses" need to be used.  But what
it is you're updating, like "emergency_buffer" and "cash" can be whatever you want
if new, or if truly being updated, needs to match something that existed before. So
if you have an emergency_buffer1 expense in your base or previous events, and
later update emergency_buffer2 expenses to 0... this won't affect emergency_buffer1
after that point in time.  So you have to be careful

** There's nothing really checking to make sure things line up properly, so it's
up to you to get the data right.

# Debugging and Understanding
* Because of all those limitations, a ton of debug is output.  In the out folder for
the user_data.json scenario, you will see.

```
user_data_expected.csv  The expected results
user_data_max.csv       The results +variance
user_data_min.csv       The results -variance
user_data.png           The plot, including min/max/variance and montecarlo analysis,
                        one sample montecarlo run, and critical events pointed out
                        on the graph (e.g. retirement).
```
