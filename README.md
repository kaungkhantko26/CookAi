# CookAI

## Project Info

- Owner: Kaung Khant Ko
- Developer: Kaung Khant Ko
- License: MIT
- Public repo setup: use `.env.example` for GitHub and keep your real `.env` private

## Overview

CookAI is a Telegram AI assistant with a split admin system:

- a user-facing chatbot
- a separate admin Telegram bot
- a web admin dashboard
- a public website terminal chat UI for `kaungkhantko.studio`

It uses OpenRouter for AI responses, supports login-based access control, and includes practical tools for writing, analysis, productivity, study, business planning, PDF export, and QR generation.

## Features

- login-gated user access with one-time hashes
- separate admin dashboard bot for user control
- web dashboard for browser-based monitoring and admin actions
- Kali-style browser terminal chat at `/bot` and `/terminal`
- plain-text AI replies without Markdown formatting in bot output
- short conversation memory with tone and persona preferences
- file and photo analysis
- PDF generation and web-page-to-PDF export
- rewrite, summarize, translate, and grammar tools
- reminders, todos, ideas, and notes
- social media content tools
- study tools
- business helper tools
- QR code generation

## Architecture

### User Bot

- handles normal chat and productivity features
- shows only limited commands before login
- supports approved users after access is granted

### Admin Bot

- creates login hashes
- monitors user activity
- approves, blocks, and unblocks users
- sends direct replies to users through the bot

### Web Dashboard

- browser-based admin panel
- password protected
- shows user status and recent activity
- supports approve, block, unblock, hash creation, and direct replies

## Project Files

- `bot.py` - main user bot
- `admin_bot.py` - admin Telegram dashboard bot
- `dashboard.py` - web admin dashboard
- `templates/terminal.html` - public website terminal chat UI
- `.env.example` - public-safe environment template for GitHub
- `.env` - local-only secrets and runtime configuration, do not upload
- `requirements.txt` - Python dependencies
- `ecosystem.config.js` - PM2 process configuration
- `LICENSE` - MIT license

## Setup

### Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
pip install -r requirements.txt
python bot.py
```

### Run With PM2

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
pip install -r requirements.txt
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

## User Bot Commands

- `/start` - confirm the bot is online
- `/help` - show commands
- `/login <hash>` - log in with a one-time access hash from the admin
- `/menu` - show the main organized button menu
- `/menu more` - show more tools in the button menu
- `/hidebuttons` - hide the button keyboard
- `/reset` - clear conversation memory and return to normal chat mode
- `/english` - switch replies back to normal English mode
- `/burmese` - switch replies into Burmese mode
- `/burmese <message>` - reply in smoother Burmese immediately
- `/persona <mode>` - set a reusable mode like coach, teacher, marketer, coder
- `/persona off` - clear the saved persona
- `/tone <text>` - save a tone sample and reuse it in future replies
- `/tone off` - clear the saved tone sample
- `/note <text>` - save a quick note
- `/note` - reply to text to save it as a note
- `/notes` - list saved notes
- `/notes delete <id>` - delete a saved note
- `/rewrite` - rewrite replied or inline text
- `/analyze` - analyze a replied photo or file
- `/analyze <question>` - analyze a replied photo or file with a specific instruction
- `/pdf` - turn a replied message or the last bot reply into a PDF
- `/pdf <text or topic>` - create a PDF from direct text or a short document request
- `/webpdf <url>` - turn a web page into a summary PDF
- `/caption` - create a social media caption
- `/hook` - create hook lines
- `/carousel` - create a carousel content outline
- `/script` - create a short video or reel script
- `/cta` - create call-to-action lines
- `/hashtags` - create relevant hashtags
- `/quiz` - create quiz questions with answers
- `/flashcards` - create study flashcards
- `/explain` - explain a topic simply
- `/exam` - create exam-style questions
- `/plan` - create a business plan draft
- `/pitch` - create a business pitch
- `/pricing` - suggest pricing structure
- `/strategy` - create a business strategy
- `/swot` - create a SWOT analysis
- `/businessmodel` - create a business model outline
- `/qr <text or link>` - create a QR code image from text or a URL
- `/shorter` - shorten replied or inline text
- `/formal` - make replied or inline text formal
- `/friendly` - make replied or inline text friendlier
- `/translate <language> | <text>` - translate text or a replied message
- `/fixgrammar` - correct grammar and wording
- `/summarize` - summarize replied or inline text
- `/remind <when> | <text>` - create a reminder
- `/reminders` - list pending reminders
- `/reminders delete <id>` - delete a reminder
- `/todo add <text>` - add a todo
- `/todo list` - show todos
- `/todo done <id>` - mark a todo done
- `/todo delete <id>` - delete a todo
- `/idea <text>` - save an idea
- `/ideas` - list saved ideas
- `/link <url>` - fetch and analyze a public link
- `/presentation` - switch the bot into presentation mode for slide-making requests
- `/presentation <topic or brief>` - switch into presentation mode and generate a slide deck draft immediately

## Admin Bot Commands

- `/start` - show admin dashboard help
- `/help` - show admin commands
- `/hash` - create a login hash
- `/users` - list known users
- `/user <id>` - inspect one user
- `/approve <id>` - approve a user ID
- `/block <id>` - block a user ID
- `/unblock <id>` - unblock a user ID
- `/replyuser <id> | <text>` - send a message to a user through the user bot

## Web Dashboard

- `dashboard.py` serves a password-protected admin dashboard
- default local bind uses `127.0.0.1:${ADMIN_DASHBOARD_PORT}`
- the dashboard shows user status, recent activity, login-hash creation, approve/block/unblock actions, and direct user replies

## Website Chat

- `dashboard.py` also serves a public terminal-style website chatbot
- local URL: `http://127.0.0.1:${ADMIN_DASHBOARD_PORT}/bot`
- website chat requests are proxied through same-origin `/api/chat`
- browser commands include `/help`, `/reset`, `/burmese`, `/english`, `/presentation`, `/link`, `/rewrite`, `/summarize`, `/caption`, `/hook`, and `/hashtags`
- `bot-dashboard.nginx.conf` maps `https://kaungkhantko.studio` to the terminal UI and keeps the chat API same-origin at `/api/chat`; `bot.kaungkhantko.top` is reserved for the admin dashboard

## Notes

- keep `.env` private and only upload `.env.example` to GitHub
- the bot uses long polling, so it does not need a webhook
- if `TELEGRAM_ADMIN_BOT_TOKEN` is set, admin controls move to the separate `admin_bot.py` process and unknown-user alerts are sent through that dashboard bot
- if `ADMIN_DASHBOARD_PASSWORD` and `ADMIN_DASHBOARD_SECRET` are set, `dashboard.py` serves a password-protected admin web dashboard
- the bot shows an organized Telegram button keyboard for common actions; use `/menu` to show it again if needed
- sending only a public URL will auto-trigger link analysis
- saved tone memory applies to both English and Burmese replies until cleared
- persona memory applies across normal chat, rewrite tools, and translation tasks until cleared
- reminders, todos, ideas, tone, persona, and language mode persist in `bot_state.json`
- simple natural phrases also work for some actions, such as `Remind me tomorrow 9am to call mom`, `Save this idea ...`, and `Add todo ...`
- messages containing the keyword `content` or `contents` get a longer social-media-style response automatically
- sending a photo or supported file will analyze it automatically; supported files include images, txt, pdf, docx, csv, and json
- `/pdf` sends back a generated PDF document file through Telegram
- `/webpdf` fetches a public web page and sends back a PDF summary
- `/qr` sends back a QR code image for the given text or link
- voice messages are disabled; use text, photos, or supported files instead
- if you want a different model, change `OPENROUTER_MODEL` in `.env`
- set `TELEGRAM_ALLOWED_USER_IDS` to a comma-separated list if more than one Telegram user should access the bot
- future users can be added without editing `.env`: the admin can create a one-time code with `/hash`, and the user can activate access with `/login <hash>`
- the admin bot automatically monitors all non-admin user inputs from the user bot and shows account details, account link, and a ready `/replyuser <id> | <text>` pattern
- before login, normal users only see `/start`, `/help`, and `/login` in the Telegram slash menu; approved users get the normal tool menu; admin controls live in the separate admin bot
- you can optionally set `TELEGRAM_ADMIN_USER_IDS` if you want more than the default admin `1201884652`
- if you want custom presentation behavior, set `PRESENTATION_SYSTEM_PROMPT` in `.env`
- you can optionally set `BURMESE_SYSTEM_PROMPT` and `LINK_ANALYSIS_SYSTEM_PROMPT` in `.env`
- the PM2 config assumes the VPS app directory will be `/root/telegram-chatbot`

## License

This project is released under the MIT License.
