# Power Automate integration

The assistant and Power Automate talk in both directions.

## 1. Assistant -> Power Automate: the "create ticket" workflow action

When a user asks the agent to open a ticket, the `create_ticket` tool POSTs the ticket to a flow.

1. In Power Automate, create an **Instant cloud flow** with the trigger
   **When an HTTP request is received**.
2. Paste [`ticket_trigger_schema.json`](ticket_trigger_schema.json) as the *Request Body JSON Schema*.
3. Add the actions you need, for example:
   - **SharePoint: Create item** in a "Service Tickets" list (Title, Description, Category, TicketId)
   - **Microsoft Teams: Post message in a chat or channel** to notify the IT/HSE/Finance team,
     using a *Switch* on `category`
   - **Response** with status code `202`
4. Save, copy the generated HTTP POST URL, and set it in `.env`:
   ```
   POWER_AUTOMATE_WEBHOOK_URL=https://prod-00.westeurope.logic.azure.com/workflows/...
   ```

Without this variable, tickets are written to `data/actions_log.jsonl` instead.

## 2. Power Automate -> Assistant: use the agent inside any flow

Any flow can call the assistant with the **HTTP** action (premium connector):

| Field | Value |
|---|---|
| Method | `POST` |
| URI | `https://<your-host>/chat` (or `/batch` for many questions) |
| Headers | `Content-Type: application/json`, `X-API-Key: <API_KEY from .env>` |
| Body | `{"message": "@{triggerBody()?['subject']}"}` |

Then use **Parse JSON** on the response, with this schema:

```json
{"type": "object", "properties": {
  "answer": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}},
  "actions": {"type": "array"}, "steps": {"type": "integer"}}}
```

Example: *When a new email arrives in the HR shared mailbox* -> HTTP `/chat` -> *Reply to email* with `answer`.

For Copilot Studio, the same endpoint can be registered as a REST API tool (custom connector),
so a Copilot Studio agent can delegate document questions to this assistant.
