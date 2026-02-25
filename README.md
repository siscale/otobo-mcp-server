# OTOBO MCP Server

An [MCP](https://modelcontextprotocol.io) server for searching and retrieving tickets from [OTOBO](https://otobo.io) via the Generic Interface REST API.

## Prerequisites

- Python 3.10+
- An OTOBO instance with the Generic Interface enabled
- [uv](https://docs.astral.sh/uv/) package manager

### OTOBO web service setup

In **Admin > Web Services**, create or edit a web service with these operations:

| Operation              | Route           | Method |
|------------------------|-----------------|--------|
| Ticket::TicketSearch   | /TicketSearch   | POST   |
| Ticket::TicketGet      | /TicketGet      | POST   |

POST is required for both — GET cannot handle the nested search parameters.

## Quickstart

```bash
git clone https://github.com/youruser/otobo-mcp-server.git
cd otobo-mcp-server

# Create environment and install dependencies
uv venv
source .venv/bin/activate
uv sync
```
Run the server:

```bash
# STDIO (default)
uv run otobo_mcp_server.py

# SSE
uv run otobo_mcp_server.py -t sse -p 8080

# Streamable HTTP
uv run otobo_mcp_server.py -t streamable-http -p 8080
```

## Configuration

All configuration is through environment variables:

| Variable           | Required | Default                      | Description                        |
|--------------------|----------|------------------------------|------------------------------------|
| `OTOBO_HOST`       | yes      |                              | Base URL, e.g. `https://otobo.example.com` |
| `OTOBO_USER`       | yes      |                              | Agent username                     |
| `OTOBO_PASSWORD`   | yes      |                              | Agent password                     |
| `OTOBO_WEBSERVICE` | no       | `GenericTicketConnectorREST` | Web service name in OTOBO admin    |
| `OTOBO_SSL_VERIFY` | no       | `true`                       | SSL certificate verification       |
| `OTOBO_TIMEOUT`    | no       | `30`                         | HTTP timeout in seconds            |
| `OTOBO_TRANSPORT`  | no       | `stdio`                      | Transport: stdio, sse, streamable-http |

For SSE/HTTP transports, bind address is set via `FASTMCP_HOST` (default `127.0.0.1`) and `FASTMCP_PORT` (default `8000`), or use `--host` / `--port` flags.

## Usage
```json
    "otobo": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/otobo-mcp-server",
        "run", "otobo_mcp_server.py"
      ],
      "env": {
        "OTOBO_HOST": "https://otobo.example.com",
        "OTOBO_USER": "api_agent",
        "OTOBO_PASSWORD": "secret"
      }
    }

```

## Usage with Claude Code

```bash
claude mcp add otobo \
  -e OTOBO_HOST=https://otobo.example.com \
  -e OTOBO_USER=api_agent \
  -e OTOBO_PASSWORD=secret \
  -- uv --directory /absolute/path/to/otobo-mcp-server run otobo_mcp_server.py
```

## Remote (SSE / Streamable HTTP)

```bash
uv run otobo_mcp_server.py -t sse --host 0.0.0.0 -p 8080
```

SSE endpoint: `http://your-host:8080/sse`
Streamable HTTP endpoint: `http://your-host:8080/mcp`

## Tools

**search_tickets** — search with filters: title keywords, date range, state, priority, customer, queue. Returns JSON with ticket details and all articles/comments.

**get_ticket_details** — fetch a single ticket by ID with dynamic fields and articles.

**get_ticket_articles** — fetch only the article/comment history for a ticket.

**check_connection** — verify OTOBO connectivity and authentication.

## Testing

```bash
# With MCP Inspector
npx @modelcontextprotocol/inspector uv run otobo_mcp_server.py
```

## License

MIT