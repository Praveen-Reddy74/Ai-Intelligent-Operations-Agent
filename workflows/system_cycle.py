from agents.analyst_agent import run_analysis_cycle
from agents.procurement_agent import run_procurement_cycle
from agents.logistics_agent import run_logistics_cycle


def run_full_operations_cycle():
    system_state = {}

    # Step 1: Analyst
    analyst_output = run_analysis_cycle()

    if analyst_output:
        system_state["trend_percent"] = analyst_output["trend_percent"]
        system_state["scrap_rate"] = analyst_output["scrap_rate"]
        system_state["analyst_summary"] = analyst_output["summary"]
    else:
        system_state["trend_percent"] = 0

    # Step 2: Procurement reacts to trend
    procurement_output = run_procurement_cycle(
        trend_percent=system_state["trend_percent"]
    )

    system_state["procurement_output"] = procurement_output

    # Step 3: Logistics check
    logistics_output = run_logistics_cycle()
    system_state["logistics_output"] = logistics_output

    return system_state