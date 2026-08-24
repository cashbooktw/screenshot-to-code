# screenshot-to-code

Convert screenshots, mockups, Figma designs, and screen recordings into clean, functional code using AI. The easiest way to try this is using <a href="https://screenshottocode.com/?utm_source=github&utm_medium=readme&utm_campaign=oss_readme&utm_content=top_cta" target="_blank" rel="noopener noreferrer">the official, hosted product at screenshottocode.com →</a>


https://github.com/user-attachments/assets/ec08a5e6-9606-41c5-b03a-1bf47dfeba75


Supported stacks:

- HTML + Tailwind
- HTML + CSS
- React + Tailwind
- Vue + Tailwind
- Bootstrap
- Ionic + Tailwind

This fork's main UI uses your local Codex CLI and ChatGPT subscription for code
generation. It does not call OpenAI, Anthropic, Gemini, or Replicate APIs.

The upstream provider integrations are still present for eval and development
tools, but `/generate-code` always runs one local Codex variant.

Upstream AI models retained for those tools:

- Gemini 3 Flash Preview and Gemini 3.1 Pro Preview - the best models
- GPT-5.5 and GPT-5.4 Mini
- Claude Opus 4.6, Claude Opus 4.8
- z-image-turbo (using Replicate) for image generation

See the [Examples](#-examples) section below for more demos.

The upstream app also supports screen recordings. Video input is not supported
by this fork's Codex CLI mode.

![google in app quick 3](https://github.com/abi/screenshot-to-code/assets/23818/8758ffa4-9483-4b9b-bb66-abd6d1594c33)

## 🛠 Getting Started

Choose the path that fits what you want to do:

- **Run locally:** best if you want to customize, self-host, or contribute.
- **Use the hosted app:** the fastest way to try Screenshot to Code with no local setup. <a href="https://screenshottocode.com/?utm_source=github&utm_medium=readme&utm_campaign=oss_readme&utm_content=getting_started_cta" target="_blank" rel="noopener noreferrer">Open the hosted app →</a>

Running locally requires the Codex CLI plus a backend/frontend setup. The app
has a React/Vite frontend and a FastAPI backend.

### Codex CLI

Install the [Codex CLI](https://developers.openai.com/codex/cli), then sign in
with the ChatGPT account that has your Codex subscription:

```bash
codex login
```

The backend finds `codex` on `PATH` by default. These environment variables are
optional and can be placed in `backend/.env`:

| Variable | Purpose |
|----------|---------|
| `CODEX_CLI_PATH` | Explicit Codex executable path, for example `/opt/homebrew/bin/codex`. An invalid explicit path is an error; it does not fall back to another CLI or an API. |
| `CODEX_MODEL` | Optional value passed to `codex exec --model`. If unset, the local Codex default is used. |
| `CODEX_REASONING_EFFORT` | Optional effort: `minimal`, `low`, `medium`, `high`, or `xhigh`. |

Run the backend (using Poetry for package management):

```bash
cd backend
# Optional when codex is not already on PATH:
echo "CODEX_CLI_PATH=/opt/homebrew/bin/codex" > .env
poetry install
poetry run uvicorn main:app --reload --port 7001
```

API keys entered in the frontend settings are ignored by `/generate-code`.
Legacy providers and eval tools keep their existing API-key behavior.

Codex CLI mode supports text or image creation and follow-up updates. It returns
one complete HTML result and does not support video, asset extraction, image
generation/editing, background removal, screenshot preview, app-specific tool
events, or token-by-token HTML streaming.

Run the frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Open http://localhost:5173 to use the app.

If you prefer to run the backend on a different port, update `VITE_WS_BACKEND_URL` in `frontend/.env.local`.

## Docker

Codex CLI mode is not supported in Docker. Run the backend directly as the same
OS user who ran `codex login`; the container does not contain the host Codex
executable or its ChatGPT login state.

## 🙋‍♂️ FAQs

- **I'm running into an error when setting up the backend. How can I fix it?** [Try this](https://github.com/abi/screenshot-to-code/issues/3#issuecomment-1814777959). If that still doesn't work, open an issue.
- **How do I get an OpenAI API key?** See https://github.com/abi/screenshot-to-code/blob/main/Troubleshooting.md
- **How can I configure an OpenAI proxy?** If you're not able to access the OpenAI API directly, for example because of country restrictions, you can try a VPN or configure the OpenAI base URL to use a proxy. Set `OPENAI_BASE_URL` in `backend/.env` or directly in the UI in the settings dialog. Make sure the URL has `v1` in the path, for example: `https://xxx.xxxxx.xxx/v1`.
- **How can I update the backend host that my frontend connects to?** Configure `VITE_HTTP_BACKEND_URL` and `VITE_WS_BACKEND_URL` in `frontend/.env.local`. For example, set `VITE_HTTP_BACKEND_URL=http://124.10.20.1:7001`.
- **Seeing UTF-8 errors when running the backend?** On Windows, open the `.env` file with Notepad++, then go to Encoding and select UTF-8.
- **How can I provide feedback?** For feedback, feature requests, and bug reports, open an issue or ping me on [Twitter](https://twitter.com/_abi_).

## 📚 Examples

**NYTimes**

| Original                                                                                                                                                        | Replica                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| <img width="1238" alt="Screenshot 2023-11-20 at 12 54 03 PM" src="https://github.com/user-attachments/assets/6b0ae86c-1b0f-4598-a578-c7b62205b3e2"> | <img width="1435" height="737" alt="Screenshot 2026-06-15 at 3 06 37 PM" src="https://github.com/user-attachments/assets/48f0ab94-5fdc-41e7-ad6e-b4ad7ef69ae1" /> |


**Instagram**

https://github.com/user-attachments/assets/a335a105-f9cc-40e6-ac6b-64e5390bfc21

**Hacker News**


https://github.com/user-attachments/assets/205cb5c7-9c3c-438d-acd4-26dfe6e077e5
