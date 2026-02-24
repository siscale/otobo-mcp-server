#!/usr/bin/env python3
"""
OTOBO MCP Server — search and retrieve tickets via the Generic Interface REST API.

Supports STDIO, SSE and Streamable HTTP transports.

Environment:
    OTOBO_HOST          Base URL, e.g. https://otobo.example.com
    OTOBO_USER          Agent username
    OTOBO_PASSWORD      Agent password
    OTOBO_WEBSERVICE    Web service name (default: GenericTicketConnectorREST)
    OTOBO_SSL_VERIFY    SSL verification (default: true)
    OTOBO_TIMEOUT       HTTP timeout in seconds (default: 30)
    OTOBO_TRANSPORT     Transport: stdio, sse, streamable-http (default: stdio)
    FASTMCP_PORT        Bind port for SSE/HTTP (default: 8000)
    FASTMCP_HOST        Bind host for SSE/HTTP (default: 127.0.0.1)
"""

import argparse
import json
import logging
import os
import sys
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

log = logging.getLogger("otobo-mcp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)


class Config:
    def __init__(self):
        self.host = os.environ.get("OTOBO_HOST", "").rstrip("/")
        self.user = os.environ.get("OTOBO_USER", "")
        self.password = os.environ.get("OTOBO_PASSWORD", "")
        self.webservice = os.environ.get("OTOBO_WEBSERVICE", "GenericTicketConnectorREST")
        self.ssl_verify = os.environ.get("OTOBO_SSL_VERIFY", "true").lower() in ("true", "1", "yes")
        self.timeout = int(os.environ.get("OTOBO_TIMEOUT", "30"))
        self.transport = os.environ.get("OTOBO_TRANSPORT", "stdio")

    def operation_url(self, operation: str) -> str:
        return f"{self.host}/otobo/nph-genericinterface.pl/Webservice/{self.webservice}/{operation}"

    def base_url(self) -> str:
        return f"{self.host}/otobo/"

    def ticket_url(self, ticket_id) -> str:
        return f"{self.host}/otobo/index.pl?Action=AgentTicketZoom;TicketID={ticket_id}"


cfg = Config()


class OtoboAPIError(Exception):
    pass


def post_operation(operation: str, payload: dict) -> dict:
    url = cfg.operation_url(operation)
    body = {"UserLogin": cfg.user, "Password": cfg.password, **payload}

    log.debug("POST %s", url)
    try:
        resp = requests.post(url, headers={"Content-Type": "application/json"},
                             data=json.dumps(body), verify=cfg.ssl_verify, timeout=cfg.timeout)
    except requests.RequestException as e:
        raise OtoboAPIError(f"Connection error: {e}") from e

    if resp.status_code != 200:
        raise OtoboAPIError(f"HTTP {resp.status_code}: {resp.reason} - {resp.text[:300]}")

    data = resp.json()
    if data.get("Error"):
        err = data["Error"]
        raise OtoboAPIError(f"{err.get('ErrorCode', '?')}: {err.get('ErrorMessage', '?')}")

    return data


def do_search(title=None, start_date=None, end_date=None,
              states=None, priorities=None, customer=None,
              queue=None, limit=50) -> list[int]:
    payload: dict[str, Any] = {"Limit": limit, "SortBy": "Created", "OrderBy": "Down"}

    if title:
        payload["Title"] = f"*{title}*"
    if start_date:
        payload["TicketCreateTimeNewerDate"] = start_date
    if end_date:
        payload["TicketCreateTimeOlderDate"] = end_date
    if states:
        payload["States"] = states if isinstance(states, list) else [states]
    if priorities:
        payload["Priorities"] = priorities if isinstance(priorities, list) else [priorities]
    if customer:
        payload["CustomerUserLogin"] = customer
    if queue:
        payload["Queues"] = [queue] if isinstance(queue, str) else queue

    log.info("TicketSearch: %s", json.dumps(payload, default=str))
    data = post_operation("TicketSearch", payload)

    ids = data.get("TicketID", [])
    if isinstance(ids, (str, int)):
        return [int(ids)]
    return [int(i) for i in ids]


def do_get_ticket(ticket_id: int, all_articles: bool = True) -> dict:
    data = post_operation("TicketGet", {
        "TicketID": str(ticket_id),
        "AllArticles": "1" if all_articles else "0",
        "DynamicFields": "1",
    })
    tickets = data.get("Ticket", [])
    if isinstance(tickets, dict):
        return tickets
    if isinstance(tickets, list) and tickets:
        return tickets[0]
    return {}


def extract_articles(ticket: dict) -> list[dict]:
    articles = ticket.get("Article", [])
    if isinstance(articles, dict):
        return [articles]
    return articles


def slim_ticket(ticket: dict, include_articles: bool = True) -> dict:
    out = {
        "ticket_id": ticket.get("TicketID"),
        "ticket_number": ticket.get("TicketNumber"),
        "title": ticket.get("Title"),
        "state": ticket.get("State"),
        "priority": ticket.get("Priority"),
        "queue": ticket.get("Queue"),
        "customer": ticket.get("CustomerUserID"),
        "owner": ticket.get("Owner"),
        "created": ticket.get("Created"),
        "changed": ticket.get("Changed"),
        "url": cfg.ticket_url(ticket["TicketID"]) if ticket.get("TicketID") else None,
    }

    dynamic = {k.replace("DynamicField_", ""): v
               for k, v in ticket.items() if k.startswith("DynamicField_") and v}
    if dynamic:
        out["dynamic_fields"] = dynamic

    if include_articles:
        out["articles"] = [slim_article(a) for a in extract_articles(ticket)]

    return out


def slim_article(article: dict) -> dict:
    return {
        "article_id": article.get("ArticleID"),
        "from": article.get("From"),
        "to": article.get("To"),
        "subject": article.get("Subject"),
        "body": article.get("Body"),
        "created": article.get("CreateTime", article.get("Created")),
        "channel": article.get("CommunicationChannel", article.get("ArticleType")),
        "sender_type": article.get("SenderType"),
    }


server = FastMCP("otobo-mcp-server")


@server.tool()
def search_tickets(
        title: str = "",
        start_date: str = "",
        end_date: str = "",
        states: str = "",
        priorities: str = "",
        customer: str = "",
        queue: str = "",
        limit: int = 50,
        include_articles: bool = True,
) -> str:
    """
    Search OTOBO tickets using filters. Returns JSON with ticket details and articles.

    Args:
        title: Keywords to match in ticket title. Wildcards applied automatically.
        start_date: Tickets created on or after this datetime. Format: YYYY-MM-DD HH:MM:SS.
        end_date: Tickets created on or before this datetime. Format: YYYY-MM-DD HH:MM:SS.
        states: Comma-separated OTOBO state names. Values: new, open, closed successful,
                closed unsuccessful, pending reminder, pending auto close+, pending auto close-,
                merged, removed.
        priorities: Comma-separated OTOBO priority names. Values: 1 very low, 2 low,
                    3 normal, 4 high, 5 very high.
        customer: Customer user login (exact match).
        queue: Queue name (exact match).
        limit: Max tickets to return, 1-200, default 50.
        include_articles: Fetch all articles per ticket. Set false for headers only.
    """
    if not cfg.host:
        return json.dumps({"error": "OTOBO_HOST is not configured"})

    limit = min(max(1, limit), 200)
    parsed_states = [s.strip() for s in states.split(",") if s.strip()] if states else None
    parsed_priorities = [p.strip() for p in priorities.split(",") if p.strip()] if priorities else None

    try:
        ticket_ids = do_search(
            title=title or None, start_date=start_date or None, end_date=end_date or None,
            states=parsed_states, priorities=parsed_priorities, customer=customer or None,
            queue=queue or None, limit=limit,
        )
    except OtoboAPIError as e:
        return json.dumps({"error": str(e)})

    if not ticket_ids:
        return json.dumps({"count": 0, "tickets": []})

    tickets = []
    errors = []
    for tid in ticket_ids:
        try:
            raw = do_get_ticket(tid, all_articles=include_articles)
            if raw:
                tickets.append(slim_ticket(raw, include_articles))
            else:
                errors.append({"ticket_id": tid, "error": "not found"})
        except OtoboAPIError as e:
            errors.append({"ticket_id": tid, "error": str(e)})

    result = {"count": len(tickets), "tickets": tickets}
    if errors:
        result["errors"] = errors
    return json.dumps(result)


@server.tool()
def get_ticket_details(ticket_id: int, include_articles: bool = True) -> str:
    """
    Get full details of a ticket by ID, including dynamic fields and all articles.

    Args:
        ticket_id: Numeric OTOBO ticket ID.
        include_articles: Include articles/comments, default true.
    """
    if not cfg.host:
        return json.dumps({"error": "OTOBO_HOST is not configured"})

    try:
        raw = do_get_ticket(ticket_id, all_articles=include_articles)
    except OtoboAPIError as e:
        return json.dumps({"error": str(e)})

    if not raw:
        return json.dumps({"error": f"Ticket {ticket_id} not found"})

    return json.dumps(slim_ticket(raw, include_articles))


@server.tool()
def get_ticket_articles(ticket_id: int) -> str:
    """
    Get the article/comment history for a specific ticket.

    Args:
        ticket_id: Numeric OTOBO ticket ID.
    """
    if not cfg.host:
        return json.dumps({"error": "OTOBO_HOST is not configured"})

    try:
        raw = do_get_ticket(ticket_id, all_articles=True)
    except OtoboAPIError as e:
        return json.dumps({"error": str(e)})

    if not raw:
        return json.dumps({"error": f"Ticket {ticket_id} not found"})

    articles = [slim_article(a) for a in extract_articles(raw)]
    return json.dumps({
        "ticket_id": raw.get("TicketID"),
        "ticket_number": raw.get("TicketNumber"),
        "title": raw.get("Title"),
        "article_count": len(articles),
        "articles": articles,
    })


@server.tool()
def check_connection() -> str:
    """Verify connectivity and authentication against the OTOBO instance."""
    if not cfg.host:
        return json.dumps({"status": "error", "message": "OTOBO_HOST is not configured"})

    http_ok = False
    try:
        resp = requests.get(cfg.base_url(), verify=cfg.ssl_verify, timeout=10)
        http_ok = resp.status_code == 200
    except requests.RequestException as e:
        return json.dumps({"status": "error", "http": False, "message": str(e)})

    try:
        post_operation("TicketSearch", {"Limit": "1"})
    except OtoboAPIError as e:
        return json.dumps({"status": "error", "http": http_ok, "auth": False, "message": str(e)})

    return json.dumps({
        "status": "ok",
        "host": cfg.host,
        "webservice": cfg.webservice,
        "user": cfg.user,
        "ssl_verify": cfg.ssl_verify,
    })


def parse_args():
    parser = argparse.ArgumentParser(description="OTOBO MCP Server")
    parser.add_argument("--transport", "-t", choices=["stdio", "sse", "streamable-http"], default=None,
                        help="Transport type (default: stdio, or set OTOBO_TRANSPORT)")
    parser.add_argument("--host", default=None, help="Bind host for SSE/HTTP (default: 127.0.0.1)")
    parser.add_argument("--port", "-p", type=int, default=None, help="Bind port for SSE/HTTP (default: 8000)")
    return parser.parse_args()


def main():
    args = parse_args()
    transport = args.transport or cfg.transport

    if args.host:
        os.environ["FASTMCP_HOST"] = args.host
    if args.port:
        os.environ["FASTMCP_PORT"] = str(args.port)
    otobo_host = cfg.host or "(not set)"
    log.info("Starting OTOBO MCP server: transport=%s otobo_host=%s webservice=%s", transport, otobo_host, cfg.webservice)

    server.run(transport=transport)


if __name__ == "__main__":
    main()
