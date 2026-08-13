# -*- coding: utf-8 -*-
"""
dashboard.py — local-only FastAPI dashboard over audit.db.

Two views:
  GET /runs/{run_id}   — run summary: funnel breakdown, latency percentiles,
                         findings grouped by severity/check.
  GET /call/{call_uuid} — per-call drilldown: turn timeline, transcript,
                         intents, per-turn latency, recording link, and the
                         raw DB rows (call_summaries/outbound_leads) next to
                         whatever findings fired for that call.

Usage: python3 dashboard.py   (serves on http://127.0.0.1:8787)
"""
import json
from collections import Counter, defaultdict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn

from db import connect

app = FastAPI()

SEVERITY_COLOR = {
    "critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04",
    "low": "#2563eb", "info": "#6b7280",
}

BASE_CSS = """
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; margin: 0; padding: 24px;
         background: #0b0d10; color: #e5e7eb; }
  @media (prefers-color-scheme: light) { body { background: #f8fafc; color: #111827; } }
  a { color: #60a5fa; text-decoration: none; }
  a:hover { text-decoration: underline; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #333; font-size: 13px; vertical-align: top; }
  th { color: #9ca3af; font-weight: 600; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; color: white; }
  .card { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
  h1, h2, h3 { margin-top: 0; }
  code, pre { background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px; font-size: 12px; }
  pre { padding: 10px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
  .muted { color: #9ca3af; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
  .stat { font-size: 24px; font-weight: 700; }
</style>
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>{BASE_CSS}</head><body>{body}</body></html>")


@app.get("/")
def root():
    conn = connect()
    row = conn.execute("SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
    conn.close()
    if row is None:
        return HTMLResponse("<p>No runs yet — run checks.py first.</p>")
    return RedirectResponse(f"/runs/{row['run_id']}")


@app.get("/runs")
def list_runs():
    conn = connect()
    rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC").fetchall()
    conn.close()
    body = "<h1>Runs</h1><table><tr><th>run_id</th><th>started</th><th>calls checked</th><th>findings</th></tr>"
    for r in rows:
        body += f"<tr><td><a href='/runs/{r['run_id']}'>{r['run_id']}</a></td><td>{r['started_at']}</td><td>{r['calls_checked']}</td><td>{r['findings_count']}</td></tr>"
    body += "</table>"
    return _page("Runs", body)


@app.get("/runs/{run_id}")
def run_summary(run_id: str):
    conn = connect()
    findings = conn.execute("SELECT * FROM findings WHERE run_id = ? ORDER BY severity, check_name", (run_id,)).fetchall()

    # Funnel breakdown
    campaign_rows = conn.execute("SELECT campaign_type, final_state, COUNT(*) c FROM call_summaries GROUP BY campaign_type, final_state ORDER BY campaign_type").fetchall()
    funnel = defaultdict(list)
    for r in campaign_rows:
        funnel[r["campaign_type"]].append((r["final_state"], r["c"]))

    latency_row = next((f for f in findings if f["check_name"] == "latency_stats"), None)

    by_severity = Counter(f["severity"] for f in findings)
    by_check = Counter(f["check_name"] for f in findings)

    conn.close()

    body = f"<h1>Run {run_id}</h1><p><a href='/runs'>&larr; all runs</a></p>"

    body += "<div class='grid'>"
    for sev in ("critical", "high", "medium", "low", "info"):
        n = by_severity.get(sev, 0)
        color = SEVERITY_COLOR[sev]
        body += f"<div class='card'><div class='stat' style='color:{color}'>{n}</div><div class='muted'>{sev}</div></div>"
    body += "</div>"

    if latency_row:
        ev = json.loads(latency_row["evidence"])
        body += f"<div class='card'><h3>Latency (substantive turns only)</h3><p>p50 = {ev['p50_ms']:.0f}ms &nbsp; p95 = {ev['p95_ms']:.0f}ms &nbsp; n = {ev['n']}</p></div>"

    body += "<div class='card'><h3>Funnel breakdown (call_summaries, by campaign_type &times; final_state)</h3><table><tr><th>campaign</th><th>final_state</th><th>count</th></tr>"
    for campaign, states in funnel.items():
        for state, c in states:
            body += f"<tr><td>{campaign}</td><td>{state}</td><td>{c}</td></tr>"
    body += "</table></div>"

    body += "<div class='card'><h3>Findings by check</h3><table><tr><th>check</th><th>count</th></tr>"
    for check, c in by_check.most_common():
        body += f"<tr><td>{check}</td><td>{c}</td></tr>"
    body += "</table></div>"

    body += "<div class='card'><h3>All findings</h3><table><tr><th>severity</th><th>check</th><th>call</th><th>summary</th></tr>"
    for f in findings:
        if f["check_name"] == "latency_stats":
            continue
        color = SEVERITY_COLOR.get(f["severity"], "#666")
        call_link = f"<a href='/call/{f['call_uuid']}'>{f['call_uuid'][:8]}</a>" if f["call_uuid"] else "-"
        body += f"<tr><td><span class='badge' style='background:{color}'>{f['severity']}</span></td><td>{f['check_name']}</td><td>{call_link}</td><td>{f['summary']}</td></tr>"
    body += "</table></div>"

    return _page(f"Run {run_id}", body)


@app.get("/call/{call_uuid}")
def call_drilldown(call_uuid: str):
    conn = connect()
    summary = conn.execute("SELECT * FROM call_summaries WHERE call_uuid = ?", (call_uuid,)).fetchone()
    log = conn.execute("SELECT * FROM call_logs WHERE call_uuid = ?", (call_uuid,)).fetchone()
    lead = None
    if summary and summary["phone_norm"]:
        lead = conn.execute("SELECT * FROM outbound_leads WHERE phone_norm = ?", (summary["phone_norm"],)).fetchone()
    events = conn.execute("SELECT * FROM audit_events WHERE call_uuid = ? ORDER BY ts", (call_uuid,)).fetchall()
    findings = conn.execute("SELECT * FROM findings WHERE call_uuid = ? ORDER BY severity", (call_uuid,)).fetchall()
    conn.close()

    body = f"<h1>Call {call_uuid}</h1><p><a href='/'>&larr; latest run</a></p>"

    if findings:
        body += "<div class='card'><h3>Findings for this call</h3><table><tr><th>severity</th><th>check</th><th>turn</th><th>summary</th></tr>"
        for f in findings:
            color = SEVERITY_COLOR.get(f["severity"], "#666")
            body += f"<tr><td><span class='badge' style='background:{color}'>{f['severity']}</span></td><td>{f['check_name']}</td><td>{f['turn'] if f['turn'] is not None else '-'}</td><td>{f['summary']}</td></tr>"
        body += "</table></div>"

    if summary:
        rec_url = summary["recording_url"] or (log["recording_url"] if log else None)
        rec_html = f"<a href='{rec_url}'>{rec_url}</a>" if rec_url else "<span class='muted'>none</span>"
        body += f"""<div class='card'><h3>Summary</h3>
        <p>campaign={summary['campaign_type']} call_number={summary['call_number']} final_state={summary['final_state']} deepest_state={summary['deepest_state']}
        turn_count={summary['turn_count']} lead_score={summary['lead_score']} lead_tier={summary['lead_tier']}
        offer_explained={bool(summary['offer_explained'])} wa_triggered={bool(summary['wa_triggered'])} cta_accepted={bool(summary['cta_accepted'])}</p>
        <p>first_response_latency={summary['first_response_latency']} avg_response_latency={summary['avg_response_latency']}</p>
        <p>recording: {rec_html}</p>
        </div>"""

    if lead:
        body += f"""<div class='card'><h3>outbound_leads (matched by phone)</h3>
        <p>status={lead['status']} dnc={bool(lead['dnc'])} funnel_type={lead['funnel_type']} campaign_type={lead['campaign_type']}
        visit_date={lead['visit_date']} visit_date_status={lead['visit_date_status']} answered_no_date_count={lead['answered_no_date_count']}</p>
        </div>"""
    else:
        body += "<div class='card muted'>No matching outbound_leads row for this call's phone.</div>"

    # Turn timeline with latency bars
    turn_latency = {}
    for e in events:
        if e["event"] == "turn_end":
            rec = json.loads(e["raw"])
            turn_latency[e["turn"]] = rec.get("latency_ms")
    if turn_latency:
        max_lat = max(v for v in turn_latency.values() if v) or 1
        body += "<div class='card'><h3>Per-turn latency</h3>"
        for turn, lat in sorted(turn_latency.items()):
            if lat is None:
                continue
            width = min(100, lat / max_lat * 100)
            body += f"<div style='margin:4px 0'><span class='muted' style='display:inline-block;width:60px'>turn {turn}</span><span style='display:inline-block;height:14px;width:{width}%;background:#3b82f6;border-radius:3px;vertical-align:middle'></span> {lat:.0f}ms</div>"
        body += "</div>"

    body += "<div class='card'><h3>Event timeline</h3><table><tr><th>ts</th><th>turn</th><th>event</th><th>detail</th></tr>"
    for e in events:
        rec = json.loads(e["raw"])
        detail = {k: v for k, v in rec.items() if k not in ("call_uuid", "turn", "event", "ts")}
        body += f"<tr><td class='muted'>{e['ts']}</td><td>{e['turn']}</td><td>{e['event']}</td><td><code>{json.dumps(detail, ensure_ascii=False)}</code></td></tr>"
    body += "</table></div>"

    if summary:
        try:
            transcript = json.loads(summary["full_transcript"] or "[]")
        except json.JSONDecodeError:
            transcript = []
        body += "<div class='card'><h3>Transcript</h3>"
        for role, text in transcript:
            who = "Priya" if role == "assistant" else "Customer"
            body += f"<p><b>{who}:</b> {text}</p>"
        body += "</div>"

    return _page(f"Call {call_uuid}", body)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8787)
