# Microsoft Teams integration (outgoing webhook)

Users @mention the assistant in a Teams channel and get the answer as a reply.

1. Deploy the service at a public HTTPS URL (Azure Container Apps, App Service or similar).
2. In Teams: **channel -> ... -> Manage channel -> Apps / Connectors -> Create an outgoing webhook**.
   - Name: `Assistant`
   - Callback URL: `https://<your-host>/integrations/teams`
3. Teams shows a **security token**. Set it in `.env`:
   ```
   TEAMS_WEBHOOK_SECRET=<token>
   ```
   Every request is then verified with the HMAC-SHA256 signature in the `Authorization` header,
   and unsigned or tampered requests get `401`.
4. In the channel: `@Assistant How quickly must a lost laptop be reported?`

Teams expects a reply within 5 seconds, so use a fast model (`OPENAI_MODEL=gpt-4o-mini`).
For a full chatbot / virtual assistant with 1:1 chats and proactive messages, register an
Azure Bot and forward its messages to `/chat`, using `session_id` as the conversation id
so the assistant keeps context.
