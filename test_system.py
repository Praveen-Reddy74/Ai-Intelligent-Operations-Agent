from workflows.system_cycle import run_full_operations_cycle

state = run_full_operations_cycle()

print("\n===== EXECUTIVE SUMMARY =====\n")
print(state.get("analyst_summary"))

print("\n===== PROCUREMENT ACTIONS =====\n")
for vendor, email in state.get("procurement_output", {}).items():
    print(f"\n--- {vendor} ---\n")
    print(email)

print("\n===== LOGISTICS REPORT =====\n")
print(state.get("logistics_output"))