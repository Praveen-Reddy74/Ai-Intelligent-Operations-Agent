from database import get_connection
from langchain_ollama import OllamaLLM


def fetch_last_7_days_production():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT production_date, item_name, units_produced, units_scrapped,
               machine_hours, downtime_minutes
        FROM production_log
        WHERE production_date >= CURRENT_DATE - INTERVAL '6 days';
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return rows


def calculate_kpis(rows):
    total_produced = sum(r[2] for r in rows)
    total_scrap = sum(r[3] for r in rows)
    total_downtime = sum(r[5] for r in rows)

    scrap_rate = (total_scrap / total_produced) * 100 if total_produced else 0

    return {
        "total_produced": total_produced,
        "total_scrap": total_scrap,
        "scrap_rate_percent": round(scrap_rate, 2),
        "total_downtime_minutes": total_downtime
    }


def detect_trend(rows):
    first_day = rows[0][2]
    last_day = rows[-1][2]

    percent_change = ((last_day - first_day) / first_day) * 100 if first_day else 0

    return round(percent_change, 2)


def generate_executive_summary(kpis, trend):
    llm = OllamaLLM(model="llama3")

    prompt = f"""
You are an operations analytics advisor.

KPIs:
{kpis}

Production growth over last 7 days: {trend}%

Write a concise executive summary.
If growth exceeds 15%, recommend raising reorder levels.
If scrap rate exceeds 5%, recommend quality review.
"""

    return llm.invoke(prompt)


def run_analysis_cycle():
    rows = fetch_last_7_days_production()

    if not rows:
        return None

    kpis = calculate_kpis(rows)
    trend = detect_trend(rows)
    summary = generate_executive_summary(kpis, trend)

    return {
        "trend_percent": trend,
        "scrap_rate": kpis["scrap_rate_percent"],
        "summary": summary
    }