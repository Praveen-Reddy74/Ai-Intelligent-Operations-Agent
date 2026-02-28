from database import get_connection
from langchain_ollama import OllamaLLM
from collections import defaultdict
from datetime import datetime, timedelta
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

# Email configuration
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "operations@company.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

# Company configuration
MANAGER_EMAIL = os.getenv("MANAGER_EMAIL", "manager@company.com")
FINANCE_EMAIL = os.getenv("FINANCE_EMAIL", "finance@company.com")
LOGISTICS_EMAIL = os.getenv("LOGISTICS_EMAIL", "logistics@company.com")


# ============================================================================
# STEP 1: READ REQUIREMENTS FROM ANALYST AGENT
# ============================================================================

def read_analyst_requirements():
    """Read the analysis report from Analyst Agent to get procurement signals"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT trend_percent, scrap_rate, summary, created_at
            FROM analyst_reports
            ORDER BY created_at DESC
            LIMIT 1;
        """)
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            return {
                "trend_percent": result[0],
                "scrap_rate": result[1],
                "summary": result[2],
                "created_at": result[3]
            }
        return None
    except Exception as e:
        print(f"Error reading analyst requirements: {e}")
        cur.close()
        conn.close()
        return None


def log_decision(agent_name, decision_summary, confidence_score, human_approved=False):
    """Log all procurement decisions"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO ai_decision_log (agent_name, decision_summary, confidence_score, human_approved)
            VALUES (%s, %s, %s, %s);
        """, (agent_name, decision_summary, confidence_score, human_approved))
        conn.commit()
    except Exception as e:
        print(f"Error logging decision: {e}")
    finally:
        cur.close()
        conn.close()


# ============================================================================
# STEP 2: CREATE RFQ MAILS AND SEND TO PREAPPROVED VENDORS
# ============================================================================

def get_low_stock_items(trend_percent=0):
    """Fetch low stock items from inventory"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT item_id, item_name, current_stock, reorder_level, unit_price
            FROM inventory
            WHERE current_stock < reorder_level;
        """)

        rows = cur.fetchall()
        return rows
    except Exception as e:
        print(f"Error fetching low stock items: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def get_preapproved_vendors(item_id):
    """Get preapproved vendors for a specific item"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT v.vendor_id, v.vendor_name, v.vendor_email, v.lead_time_days,
                   iv.unit_price, iv.rating
            FROM vendors v
            JOIN inventory_vendors iv ON v.vendor_id = iv.vendor_id
            WHERE iv.item_id = %s AND v.is_approved = TRUE
            ORDER BY iv.rating DESC;
        """, (item_id,))

        vendors = cur.fetchall()
        return vendors
    except Exception as e:
        print(f"Error fetching vendors: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def generate_rfq_email(vendor_name, vendor_email, items_list):
    """Generate RFQ email content using LLM"""
    llm = OllamaLLM(model="llama3")

    prompt = f"""
You are a professional procurement specialist.

Generate a Request for Quotation (RFQ) email to {vendor_name} ({vendor_email}).

Items requested:
{items_list}

Requirements:
- Professional RFQ format
- Include clear item descriptions and quantities
- Request quote validity period (30 days)
- Request delivery timeline
- Include company contact information
- Set response deadline (5 business days)
- One email only, no duplicates

Generate the email body:
"""

    try:
        response = llm.invoke(prompt)
        return response
    except Exception as e:
        print(f"Error generating RFQ email: {e}")
        return None


def send_email(recipient_email, subject, body):
    """Send email via SMTP"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        print(f"Email sent successfully to {recipient_email}")
        return True
    except Exception as e:
        print(f"Error sending email to {recipient_email}: {e}")
        return False


def create_rfq_record(item_id, vendor_id, rfq_number, required_qty):
    """Create RFQ record in database"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO rfqs (item_id, vendor_id, rfq_number, required_qty, status, created_date)
            VALUES (%s, %s, %s, %s, 'PENDING', NOW())
            RETURNING rfq_id;
        """, (item_id, vendor_id, rfq_number, required_qty))

        rfq_id = cur.fetchone()[0]
        conn.commit()
        return rfq_id
    except Exception as e:
        print(f"Error creating RFQ record: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def send_rfq_to_vendors(requirement_data):
    """STEP 2: Create and send RFQ emails to preapproved vendors"""
    low_items = get_low_stock_items(requirement_data.get("trend_percent", 0))
    
    if not low_items:
        print("No low stock items found")
        return {"rfqs_sent": 0, "details": []}

    rfqs_sent = 0
    rfq_details = []

    for item in low_items:
        item_id, item_name, current_stock, reorder_level, unit_price = item

        # Calculate required quantity
        adjusted_reorder = reorder_level
        if requirement_data.get("trend_percent", 0) > 15:
            adjusted_reorder = int(reorder_level * 1.2)

        required_qty = adjusted_reorder - current_stock

        # Get preapproved vendors
        vendors = get_preapproved_vendors(item_id)

        if not vendors:
            print(f"No approved vendors found for {item_name}")
            continue

        # Send RFQ to each vendor
        for vendor in vendors:
            vendor_id, vendor_name, vendor_email, lead_time, price, rating = vendor

            rfq_number = f"RFQ-{datetime.now().strftime('%Y%m%d%H%M%S')}-{item_id}-{vendor_id}"

            items_list = f"""
            Item: {item_name}
            Quantity: {required_qty} units
            Unit Price Range: ${unit_price}
            Lead Time: {lead_time} days
            """

            rfq_content = generate_rfq_email(vendor_name, vendor_email, items_list)

            if rfq_content:
                subject = f"Request for Quotation (RFQ) - {rfq_number}"
                
                if send_email(vendor_email, subject, rfq_content):
                    rfq_id = create_rfq_record(item_id, vendor_id, rfq_number, required_qty)
                    
                    if rfq_id:
                        rfqs_sent += 1
                        rfq_details.append({
                            "rfq_number": rfq_number,
                            "item_name": item_name,
                            "vendor_name": vendor_name,
                            "required_qty": required_qty,
                            "status": "SENT"
                        })

                        log_decision(
                            agent_name="Procurement Agent - RFQ",
                            decision_summary=f"RFQ sent to {vendor_name} for {item_name} (Qty: {required_qty})",
                            confidence_score=0.9,
                            human_approved=False
                        )

    return {"rfqs_sent": rfqs_sent, "details": rfq_details}


# ============================================================================
# STEP 3: PERIODICALLY CHECK INBOX FOR QUOTES
# ============================================================================

def fetch_pending_rfqs():
    """Fetch all pending RFQs awaiting quotes"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT rfq_id, item_id, vendor_id, rfq_number, required_qty, created_date
            FROM rfqs
            WHERE status = 'PENDING'
            AND created_date <= NOW() - INTERVAL '1 day'
            ORDER BY created_date ASC;
        """)

        pending_rfqs = cur.fetchall()
        return pending_rfqs
    except Exception as e:
        print(f"Error fetching pending RFQs: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def check_for_quotes_inbox():
    """STEP 3: Check inbox for vendor quotes (simulated via database)"""
    # In a real scenario, this would integrate with email APIs (Gmail, Outlook)
    # For now, we simulate quote receipt
    
    pending_rfqs = fetch_pending_rfqs()
    quotes_received = 0
    quote_details = []

    for rfq in pending_rfqs:
        rfq_id, item_id, vendor_id, rfq_number, required_qty, created_date = rfq

        # Simulate checking for quote in database
        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT quote_id, vendor_id, quote_price, delivery_days, validity_days
                FROM vendor_quotes
                WHERE rfq_id = %s AND status = 'RECEIVED'
                LIMIT 1;
            """, (rfq_id,))

            quote_data = cur.fetchone()

            if quote_data:
                quote_id, vendor_id_quote, quote_price, delivery_days, validity_days = quote_data

                # Update RFQ status
                cur.execute("""
                    UPDATE rfqs
                    SET status = 'QUOTED'
                    WHERE rfq_id = %s;
                """, (rfq_id,))
                conn.commit()

                quotes_received += 1
                quote_details.append({
                    "rfq_number": rfq_number,
                    "vendor_id": vendor_id_quote,
                    "quote_price": quote_price,
                    "delivery_days": delivery_days,
                    "quote_id": quote_id
                })

        except Exception as e:
            print(f"Error checking quotes: {e}")
        finally:
            cur.close()
            conn.close()

    return {"quotes_received": quotes_received, "quote_details": quote_details}


# ============================================================================
# STEP 4: COMPARE QUOTES AND SUGGEST TOP QUOTE
# ============================================================================

def compare_and_rank_quotes(item_id):
    """Compare all quotes for an item and rank them"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT vq.quote_id, vq.vendor_id, v.vendor_name, vq.quote_price, 
                   vq.delivery_days, vq.validity_days, iv.rating
            FROM vendor_quotes vq
            JOIN vendors v ON vq.vendor_id = v.vendor_id
            JOIN inventory_vendors iv ON iv.vendor_id = v.vendor_id
            WHERE vq.rfq_id = (
                SELECT rfq_id FROM rfqs WHERE item_id = %s AND status = 'QUOTED'
                ORDER BY created_date DESC LIMIT 1
            )
            ORDER BY vq.quote_price ASC;
        """, (item_id,))

        quotes = cur.fetchall()
        return quotes
    except Exception as e:
        print(f"Error comparing quotes: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def generate_quote_analysis(quotes_data, item_name):
    """Use LLM to analyze and recommend best quote"""
    llm = OllamaLLM(model="llama3")

    prompt = f"""
You are a procurement analyst.

Analyze these vendor quotes for {item_name}:

{quotes_data}

Criteria for evaluation:
1. Price competitiveness (40% weight)
2. Delivery timeline (30% weight)
3. Vendor rating/reliability (30% weight)

Provide:
- Top recommendation with justification
- Risk assessment for top 3 quotes
- Cost-benefit analysis
- Final recommendation score (0-100)

Be concise and data-driven.
"""

    try:
        response = llm.invoke(prompt)
        return response
    except Exception as e:
        print(f"Error generating quote analysis: {e}")
        return None


def select_best_quote(item_id):
    """STEP 4: Compare quotes and suggest top quote"""
    quotes = compare_and_rank_quotes(item_id)

    if not quotes:
        return {"status": "no_quotes", "recommendation": None}

    # Prepare data for LLM analysis
    quotes_formatted = "\n".join([
        f"Vendor: {q[2]}, Price: ${q[3]}, Delivery: {q[4]} days, Rating: {q[6]}/5"
        for q in quotes
    ])

    # Get item name
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT item_name FROM inventory WHERE item_id = %s", (item_id,))
    item_result = cur.fetchone()
    cur.close()
    conn.close()

    item_name = item_result[0] if item_result else "Unknown Item"

    analysis = generate_quote_analysis(quotes_formatted, item_name)

    # Select the cheapest quote as default
    best_quote = quotes[0]
    quote_id = best_quote[0]

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE vendor_quotes
            SET status = 'SELECTED'
            WHERE quote_id = %s;
        """, (quote_id,))
        
        cur.execute("""
            UPDATE vendor_quotes
            SET status = 'REJECTED'
            WHERE quote_id != %s AND rfq_id = (
                SELECT rfq_id FROM vendor_quotes WHERE quote_id = %s
            );
        """, (quote_id, quote_id))
        
        conn.commit()

        log_decision(
            agent_name="Procurement Agent - Quote Analysis",
            decision_summary=f"Best quote selected: {best_quote[2]} at ${best_quote[3]}",
            confidence_score=0.92,
            human_approved=False
        )

    except Exception as e:
        print(f"Error selecting quote: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

    return {
        "status": "selected",
        "selected_quote": {
            "vendor_id": best_quote[1],
            "vendor_name": best_quote[2],
            "price": best_quote[3],
            "delivery_days": best_quote[4],
            "quote_id": quote_id
        },
        "analysis": analysis
    }


# ============================================================================
# STEP 5: SEND APPROVAL REQUEST TO MIDLEVEL MANAGER
# ============================================================================

def generate_approval_request_email(item_name, vendor_name, quote_price, delivery_days, analysis):
    """Generate approval request email for manager"""
    llm = OllamaLLM(model="llama3")

    prompt = f"""
You are a procurement manager requesting purchase approval.

Generate a professional approval request email to the midlevel manager.

Details:
- Item: {item_name}
- Vendor: {vendor_name}
- Quote Price: ${quote_price}
- Delivery Time: {delivery_days} days
- Analysis: {analysis}

Email should include:
- Clear item and vendor details
- Cost justification
- Delivery timeline impact
- Risk assessment
- Approval request with decision deadline (next business day)
- Next steps after approval

Be professional and concise.
"""

    try:
        response = llm.invoke(prompt)
        return response
    except Exception as e:
        print(f"Error generating approval email: {e}")
        return None


def create_approval_record(quote_id):
    """Create approval tracking record"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO purchase_approvals (quote_id, requested_date, status, manager_email)
            VALUES (%s, NOW(), 'PENDING', %s)
            RETURNING approval_id;
        """, (quote_id, MANAGER_EMAIL))

        approval_id = cur.fetchone()[0]
        conn.commit()
        return approval_id
    except Exception as e:
        print(f"Error creating approval record: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def request_purchase_approval(quote_data):
    """STEP 5: Send approval request to midlevel manager"""
    vendor_name = quote_data.get("vendor_name")
    quote_price = quote_data.get("price")
    delivery_days = quote_data.get("delivery_days")
    analysis = quote_data.get("analysis", "No analysis available")
    
    # Get item name from quote
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT i.item_name
        FROM inventory i
        JOIN rfqs r ON r.item_id = i.item_id
        JOIN vendor_quotes vq ON vq.rfq_id = r.rfq_id
        WHERE vq.quote_id = %s
    """, (quote_data.get("quote_id"),))
    
    result = cur.fetchone()
    item_name = result[0] if result else "Unknown Item"
    cur.close()
    conn.close()

    approval_email = generate_approval_request_email(item_name, vendor_name, quote_price, delivery_days, analysis)

    if approval_email:
        subject = f"Purchase Approval Request - {item_name} from {vendor_name}"

        if send_email(MANAGER_EMAIL, subject, approval_email):
            approval_id = create_approval_record(quote_data.get("quote_id"))

            if approval_id:
                log_decision(
                    agent_name="Procurement Agent - Approval",
                    decision_summary=f"Approval request sent to manager for {item_name} - Quote: ${quote_price}",
                    confidence_score=0.95,
                    human_approved=False
                )

                return {
                    "status": "approval_requested",
                    "approval_id": approval_id,
                    "manager_email": MANAGER_EMAIL
                }

    return {"status": "failed", "approval_id": None}


# ============================================================================
# STEP 6: SEND PURCHASE ORDER AND PAYMENT REQUEST TO FINANCE
# ============================================================================

def check_approval_status(approval_id):
    """Check if purchase approval has been granted"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT status, approved_date
            FROM purchase_approvals
            WHERE approval_id = %s;
        """, (approval_id,))

        result = cur.fetchone()
        return result
    except Exception as e:
        print(f"Error checking approval: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def generate_purchase_order(quote_id, approved=True):
    """Generate purchase order document"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT i.item_name, i.item_id, r.required_qty, vq.quote_price, v.vendor_name,
                   v.vendor_email, v.payment_terms, vq.delivery_days
            FROM vendor_quotes vq
            JOIN rfqs r ON vq.rfq_id = r.rfq_id
            JOIN inventory i ON r.item_id = i.item_id
            JOIN vendors v ON vq.vendor_id = v.vendor_id
            WHERE vq.quote_id = %s;
        """, (quote_id,))

        po_data = cur.fetchone()

        if po_data:
            item_name, item_id, qty, price, vendor_name, vendor_email, payment_terms, delivery_days = po_data

            po_number = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{item_id}"
            total_amount = qty * price

            po_content = f"""
PURCHASE ORDER

PO Number: {po_number}
Date: {datetime.now().strftime('%Y-%m-%d')}
Vendor: {vendor_name}
Vendor Email: {vendor_email}

Item Description: {item_name}
Quantity: {qty}
Unit Price: ${price}
Total Amount: ${total_amount:.2f}

Delivery Timeline: {delivery_days} days
Payment Terms: {payment_terms}
Expected Delivery Date: {(datetime.now() + timedelta(days=delivery_days)).strftime('%Y-%m-%d')}

Special Instructions:
- Quality inspection required upon delivery
- Please confirm receipt of this PO within 48 hours
- Any changes require written approval

Thank you for your business.
"""
            return {
                "po_number": po_number,
                "po_content": po_content,
                "total_amount": total_amount,
                "vendor_email": vendor_email,
                "vendor_name": vendor_name
            }
    except Exception as e:
        print(f"Error generating PO: {e}")
    finally:
        cur.close()
        conn.close()

    return None


def generate_payment_request_email(po_data, payment_method="Bank Transfer"):
    """Generate payment request email for finance"""
    llm = OllamaLLM(model="llama3")

    prompt = f"""
You are a procurement finance coordinator.

Generate a payment request/authorization email to the finance department.

PO Details:
- PO Number: {po_data.get('po_number')}
- Vendor: {po_data.get('vendor_name')}
- Amount: ${po_data.get('total_amount')}
- Payment Terms: NET 30

Email should include:
- Clear invoice/payment details
- Account coding information
- Vendor bank details request
- Payment timeline (process within 3 business days)
- Approval chain reference
- Contact information for clarifications

Keep it professional and concise.
"""

    try:
        response = llm.invoke(prompt)
        return response
    except Exception as e:
        print(f"Error generating payment email: {e}")
        return None


def create_purchase_order_record(quote_id, po_number, total_amount):
    """Create PO record in database"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO purchase_orders (quote_id, po_number, po_date, amount, status)
            VALUES (%s, %s, NOW(), %s, 'ISSUED')
            RETURNING po_id;
        """, (quote_id, po_number, total_amount))

        po_id = cur.fetchone()[0]
        conn.commit()
        return po_id
    except Exception as e:
        print(f"Error creating PO record: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def finalize_purchase_order(quote_id):
    """STEP 6: Send purchase order and payment request to finance"""
    
    # Check approval status first
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT pa.status
            FROM purchase_approvals pa
            WHERE pa.quote_id = %s
            ORDER BY pa.requested_date DESC
            LIMIT 1;
        """, (quote_id,))
        
        approval_result = cur.fetchone()
        
        if not approval_result or approval_result[0] != 'APPROVED':
            cur.close()
            conn.close()
            return {"status": "not_approved", "message": "Awaiting manager approval"}
        
    finally:
        cur.close()
        conn.close()

    # Generate PO
    po_data = generate_purchase_order(quote_id)

    if not po_data:
        return {"status": "failed", "message": "Could not generate PO"}

    # Send PO to vendor
    po_subject = f"Purchase Order - {po_data['po_number']}"
    po_sent = send_email(po_data['vendor_email'], po_subject, po_data['po_content'])

    if not po_sent:
        return {"status": "failed", "message": "Could not send PO to vendor"}

    # Generate and send payment request to finance
    payment_email = generate_payment_request_email(po_data)

    if payment_email:
        payment_subject = f"Payment Authorization Required - {po_data['po_number']}"
        payment_sent = send_email(FINANCE_EMAIL, payment_subject, payment_email)

        if payment_sent:
            po_id = create_purchase_order_record(quote_id, po_data['po_number'], po_data['total_amount'])

            if po_id:
                log_decision(
                    agent_name="Procurement Agent - PO Finalization",
                    decision_summary=f"PO issued: {po_data['po_number']} for ${po_data['total_amount']:.2f}",
                    confidence_score=0.98,
                    human_approved=True
                )

                return {
                    "status": "po_finalized",
                    "po_number": po_data['po_number'],
                    "po_id": po_id,
                    "total_amount": po_data['total_amount'],
                    "vendor_name": po_data['vendor_name']
                }

    return {"status": "partial_failure", "message": "PO sent but payment request failed"}


# ============================================================================
# STEP 7: FORWARD DETAILS TO LOGISTICS AGENT
# ============================================================================

def get_po_details(po_id):
    """Retrieve complete PO details"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT po.po_number, po.po_date, po.amount, i.item_name, r.required_qty,
                   v.vendor_name, vq.delivery_days, vq.quote_price
            FROM purchase_orders po
            JOIN vendor_quotes vq ON po.quote_id = vq.quote_id
            JOIN rfqs r ON vq.rfq_id = r.rfq_id
            JOIN inventory i ON r.item_id = i.item_id
            JOIN vendors v ON vq.vendor_id = v.vendor_id
            WHERE po.po_id = %s;
        """, (po_id,))

        po_details = cur.fetchone()
        return po_details
    except Exception as e:
        print(f"Error fetching PO details: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def generate_logistics_handoff_email(po_details):
    """Generate handoff email for logistics agent"""
    llm = OllamaLLM(model="llama3")

    po_number, po_date, amount, item_name, qty, vendor_name, delivery_days, unit_price = po_details

    expected_delivery = (datetime.now() + timedelta(days=delivery_days)).strftime('%Y-%m-%d')

    prompt = f"""
You are a procurement specialist handing off a purchase order to logistics.

Generate a detailed handoff email to the logistics team.

PO Information:
- PO Number: {po_number}
- Vendor: {vendor_name}
- Item: {item_name}
- Quantity: {qty}
- Total Amount: ${amount}
- Expected Delivery: {expected_delivery}
- Lead Time: {delivery_days} days

Email should include:
- Clear identification of the purchase order
- Item and vendor details
- Expected delivery date and timeline
- Quantity and specifications
- Instructions for receiving and inspection
- Follow-up requirements (tracking, status updates)
- Contact information for shipment issues
- Quality inspection checklist reference

Make it action-oriented and clear.
"""

    try:
        response = llm.invoke(prompt)
        return response
    except Exception as e:
        print(f"Error generating logistics email: {e}")
        return None


def create_shipment_tracking_record(po_id, po_number):
    """Create shipment tracking record for logistics"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO shipment_schedule (po_number, expected_arrival, status, quantity)
            VALUES (%s, NOW() + INTERVAL '14 days', 'IN_TRANSIT', 0)
            RETURNING shipment_id;
        """, (po_number,))

        shipment_id = cur.fetchone()[0]
        conn.commit()
        return shipment_id
    except Exception as e:
        print(f"Error creating shipment record: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def forward_to_logistics_agent(po_id):
    """STEP 7: Forward finalized order details to logistics agent"""
    
    po_details = get_po_details(po_id)

    if not po_details:
        return {"status": "failed", "message": "Could not retrieve PO details"}

    logistics_email = generate_logistics_handoff_email(po_details)

    if logistics_email:
        subject = f"Purchase Order Handoff for Logistics Tracking - {po_details[0]}"

        if send_email(LOGISTICS_EMAIL, subject, logistics_email):
            shipment_id = create_shipment_tracking_record(po_id, po_details[0])

            if shipment_id:
                log_decision(
                    agent_name="Procurement Agent - Logistics Handoff",
                    decision_summary=f"PO {po_details[0]} forwarded to logistics for item {po_details[3]}",
                    confidence_score=0.97,
                    human_approved=False
                )

                return {
                    "status": "forwarded",
                    "po_number": po_details[0],
                    "shipment_id": shipment_id,
                    "logistics_email": LOGISTICS_EMAIL,
                    "expected_delivery": (datetime.now() + timedelta(days=po_details[6])).strftime('%Y-%m-%d')
                }

    return {"status": "failed", "message": "Could not send to logistics"}


# ============================================================================
# MAIN PROCUREMENT CYCLE - ALL STEPS
# ============================================================================

def run_procurement_cycle(analyst_report=None):
    """Run complete 7-step procurement cycle"""
    
    print("\n" + "="*70)
    print("STARTING PROCUREMENT AGENT CYCLE")
    print("="*70)

    # STEP 1: Read analyst requirements
    print("\n[STEP 1] Reading requirements from Analyst Agent...")
    requirement_data = analyst_report or read_analyst_requirements()

    if not requirement_data:
        print("No analyst report available. Using default parameters.")
        requirement_data = {"trend_percent": 0, "summary": "Standard procurement"}

    print(f"✓ Analyst Report: Trend={requirement_data.get('trend_percent')}%, Scrap={requirement_data.get('scrap_rate')}%")

    # STEP 2: Send RFQs
    print("\n[STEP 2] Creating and sending RFQs to preapproved vendors...")
    rfq_result = send_rfq_to_vendors(requirement_data)
    print(f"✓ RFQs Sent: {rfq_result['rfqs_sent']} RFQs")

    if rfq_result['rfqs_sent'] == 0:
        print("No RFQs sent. Exiting cycle.")
        return {
            "cycle_status": "no_action",
            "steps_completed": 1
        }

    # STEP 3: Check for quotes
    print("\n[STEP 3] Checking inbox for vendor quotes...")
    quotes_result = check_for_quotes_inbox()
    print(f"✓ Quotes Received: {quotes_result['quotes_received']} quotes")

    if quotes_result['quotes_received'] == 0:
        print("No quotes received yet. Will retry in next cycle.")
        return {
            "cycle_status": "awaiting_quotes",
            "rfqs_sent": rfq_result['rfqs_sent'],
            "steps_completed": 2
        }

    # STEP 4: Compare and rank quotes
    print("\n[STEP 4] Comparing quotes and selecting best offer...")
    # Get first low stock item for quote comparison
    low_items = get_low_stock_items()
    if low_items:
        first_item_id = low_items[0][0]
        quote_result = select_best_quote(first_item_id)
        print(f"✓ Best Quote Selected: {quote_result.get('selected_quote', {}).get('vendor_name')} @ ${quote_result.get('selected_quote', {}).get('price')}")
    else:
        print("No items to process")
        return {"cycle_status": "error", "message": "No items found"}

    # STEP 5: Request approval
    print("\n[STEP 5] Requesting purchase approval from manager...")
    approval_result = request_purchase_approval(quote_result.get('selected_quote', {}))
    print(f"✓ Approval Request Sent to: {approval_result.get('manager_email')}")

    # STEP 6: Finalize PO and send to finance
    print("\n[STEP 6] Finalizing purchase order and sending to finance...")
    po_result = finalize_purchase_order(quote_result.get('selected_quote', {}).get('quote_id'))
    
    if po_result.get('status') == 'not_approved':
        print("⚠ Awaiting manager approval before issuing PO")
    elif po_result.get('status') == 'po_finalized':
        print(f"✓ PO Finalized: {po_result.get('po_number')} for ${po_result.get('total_amount'):.2f}")

        # STEP 7: Forward to logistics
        print("\n[STEP 7] Forwarding order details to logistics agent...")
        logistics_result = forward_to_logistics_agent(po_result.get('po_id'))
        print(f"✓ Order forwarded to Logistics. Expected Delivery: {logistics_result.get('expected_delivery')}")

        print("\n" + "="*70)
        print("PROCUREMENT CYCLE COMPLETED SUCCESSFULLY")
        print("="*70)

        return {
            "cycle_status": "completed",
            "rfqs_sent": rfq_result['rfqs_sent'],
            "quotes_received": quotes_result['quotes_received'],
            "po_number": po_result.get('po_number'),
            "amount": po_result.get('total_amount'),
            "logistics_handoff": logistics_result.get('status'),
            "steps_completed": 7
        }
    else:
        print(f"⚠ PO Status: {po_result.get('status')}")

    return {
        "cycle_status": "partial",
        "rfqs_sent": rfq_result['rfqs_sent'],
        "quotes_received": quotes_result['quotes_received'],
        "po_status": po_result.get('status'),
        "steps_completed": 6
    }