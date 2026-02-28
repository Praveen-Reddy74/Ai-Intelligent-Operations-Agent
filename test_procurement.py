from agents.procurement_agent import run_procurement_cycle

result = run_procurement_cycle()

for vendor, email_content in result.items():
    print("\n==============================")
    print(f"Vendor: {vendor}")
    print("==============================\n")
    print(email_content)