from database import get_connection
from langchain_ollama import OllamaLLM
from collections import defaultdict


def log_decision(agent_name, decision_summary, confidence_score, human_approved=False):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO ai_decision_log (agent_name, decision_summary, confidence_score, human_approved)
        VALUES (%s, %s, %s, %s);
    """, (agent_name, decision_summary, confidence_score, human_approved))

    conn.commit()
    cur.close()
    conn.close()


def get_low_stock_items():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT item_name, current_stock, reorder_level, vendor_email, unit_price
        FROM inventory
        WHERE current_stock < reorder_level;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return rows


def calculate_and_group_by_vendor(rows, trend_percent=0):
    vendor_map = defaultdict(list)

    for item in rows:
        item_name, current_stock, reorder_level, vendor_email, unit_price = item

        # --- Trend-based adjustment ---
        adjusted_reorder = reorder_level

        if trend_percent > 15:
            adjusted_reorder = int(reorder_level * 1.2)

        order_qty = adjusted_reorder - current_stock

        # Prevent negative ordering
        if order_qty <= 0:
            continue

        total_cost = order_qty * float(unit_price)

        vendor_map[vendor_email].append({
            "item_name": item_name,
            "order_quantity": order_qty,
            "unit_price": float(unit_price),
            "total_cost": total_cost
        })

    return vendor_map


def generate_vendor_email(vendor_email, items):
    llm = OllamaLLM(model="llama3")

    prompt = f"""
You are a professional procurement manager.

Generate ONE clean purchase order email to {vendor_email}.

Rules:
- One greeting only.
- Include only the items listed.
- No placeholders.
- Be concise and professional.

Items to order:
{items}
"""

    response = llm.invoke(prompt)
    return response


def run_procurement_cycle(trend_percent=0):
    low_items = get_low_stock_items()

    if not low_items:
        return {}

    vendor_map = calculate_and_group_by_vendor(low_items, trend_percent)

    vendor_emails_output = {}

    for vendor_email, items in vendor_map.items():
        email_content = generate_vendor_email(vendor_email, items)

        total_value = sum(i['total_cost'] for i in items)

        log_decision(
            agent_name="Procurement Agent",
            decision_summary=f"PO generated for {vendor_email} with {len(items)} items totaling ${total_value:.2f}",
            confidence_score=0.95,
            human_approved=False
        )

        vendor_emails_output[vendor_email] = email_content

    return vendor_emails_output