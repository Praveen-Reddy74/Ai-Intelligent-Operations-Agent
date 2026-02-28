from workflows.system_cycle import run_full_operations_cycle
import datetime


def run_morning_cycle():
    print("\n=======================================")
    print("AI OPERATIONS MORNING CYCLE")
    print("Date:", datetime.date.today())
    print("=======================================\n")

    # IMPORTANT: Actually call the system cycle
    state = run_full_operations_cycle()

    print("\n===== EXECUTIVE SUMMARY =====\n")
    print(state.get("analyst_summary"))

    print("\n===== PROCUREMENT ACTIONS =====\n")
    procurement_output = state.get("procurement_output", {})

    if not procurement_output:
        print("No procurement actions required.")
    else:
        for vendor, email in procurement_output.items():
            print(f"\n--- {vendor} ---\n")
            print(email)

    print("\n===== LOGISTICS REPORT =====\n")
    print(state.get("logistics_output"))

    print("\n===== ROI ESTIMATION =====\n")
    roi = state.get("roi", {})
    print(f"Estimated Total Value Created: ${roi.get('total_savings', 0):,.2f}")

    print("\n=======================================\n")


if __name__ == "__main__":
    run_morning_cycle()