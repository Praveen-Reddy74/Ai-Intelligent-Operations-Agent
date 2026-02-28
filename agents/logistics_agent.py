from database import get_connection
from langchain_ollama import OllamaLLM


def fetch_shipments():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT item_name, expected_arrival, quantity, carrier, status
        FROM shipment_schedule;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return rows


def assess_logistics_risk(shipments):
    risk_flags = []

    for shipment in shipments:
        item_name, arrival, quantity, carrier, status = shipment

        if status != "Delivered":
            risk_flags.append({
                "item_name": item_name,
                "arrival_date": str(arrival),
                "carrier": carrier,
                "status": status
            })

    return risk_flags


def generate_logistics_report(risks):
    llm = OllamaLLM(model="llama3")

    prompt = f"""
You are a logistics operations coordinator.

The following shipments are currently in transit:

{risks}

Assess if there are potential delivery risks.
If delay could impact production, recommend mitigation strategies 
such as expediting shipment or alternative sourcing.

Provide a concise operational report.
"""

    return llm.invoke(prompt)


def run_logistics_cycle():
    shipments = fetch_shipments()

    if not shipments:
        return "No shipment data available."

    risks = assess_logistics_risk(shipments)
    report = generate_logistics_report(risks)

    return report