# Image-aware workflow assistant

**Ask AI** opens a side panel for questions about preprocessing, regions, candidate review, channels and neurite measurements. The integration is implemented; a provider is not configured by default.

On Send, the assistant can attach the current displayed image and an acquired raw-source snapshot, resized to at most 1024 pixels on the longest side. Review attaches its XY result plane; a Process preview attaches its candidate outlines and records the preview's channel, bounds and Z. The checkbox can disable image attachment. The panel shows the snapshots sent. Questions, image context and attached snapshots go to the configured provider only when Send is pressed. Local scientific processing and saved workspaces keep their existing storage behavior.

Answers can propose a bounded draft: workspace, channel, technique, scope, working resolution, preprocessing settings and explicit region coordinates. **Apply draft** changes the form. Numeric preprocessing suggestions disclose their working-grid units; existing physical settings stay unchanged when no numeric settings are proposed. Full-image and selected-region drafts are explicit. Previewing, running, exporting, deleting or accepting candidates remain separate user actions. Exact region coordinates are validated against image dimensions and working resolution. Images, workspace text and assistant responses cannot execute code or invoke unrestricted platform tools.

## Native server

Configure server-side `OPENAI_API_KEY`, a separate random `FIELD_ASSISTANT_TOKEN` of at least 24 characters, and optionally `FIELD_ASSISTANT_MODEL`. The default model is `gpt-5.4-mini`. Enter the separate access token under **Connect assistant**. Provider credentials never belong in the browser or workspace. Native assistant chat checks this token before contacting the provider. The adapter uses the OpenAI Responses API with image inputs, a strict answer/draft schema and `store=false`. `FIELD_ASSISTANT_API_URL` can select another compatible HTTPS Responses endpoint or a local development endpoint.

No live provider call was made during implementation. Tests use a mocked transport; browser verification used a local mock server to confirm two real PNG snapshots and draft application.

## Static browser demo

The static app keeps its Python processing in a browser worker and cannot hold a provider secret. Use the optional gateway on a trusted local machine:

```sh
# Configure OPENAI_API_KEY and a separate random FIELD_ASSISTANT_TOKEN in the environment.
.venv/bin/python tools/assistant_gateway.py --port 8788 --origin https://YOUR-STUDIO-ORIGIN
```

In **Ask AI → Connect assistant**, enter `http://127.0.0.1:8788` and the separate gateway access token. Use the exact origin of the studio tab. The gateway binds only to loopback, checks Host, Origin and token, limits payload size, and exposes only assistance routes. It does not open source files or modify the studio workspace. The gateway token lasts for the browser session; only the gateway URL is saved locally.

The assistant interprets images as workflow evidence. It cannot certify cell identity, accurate counts, neuron ownership or lengths from an image. Numeric scientific results come from processing and reviewed measurements.

Provider contracts: [image inputs](https://developers.openai.com/api/docs/guides/images-vision), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
