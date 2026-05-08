# SSD/NAND Firmware Knowledge Assistant

This project is an industrial-style AI assistant for SSD/NAND firmware, validation, and RMA troubleshooting workflows. It is designed as a Maistorage portfolio project: useful enough to demonstrate real engineering value, but still simple enough to run locally and explain in an interview.

## Industry Problem

Firmware and validation teams often debug issues using scattered sources:

- NAND read-retry notes
- Host timeout logs
- FTL garbage-collection behavior
- wear-leveling and block retirement rules
- power-loss recovery checklists
- thermal reset analysis
- RMA summaries and customer issue notes

Manual search is slow, and unsupported AI answers can be risky. This tool focuses on grounded answers, citations, evidence confidence, subsystem classification, and next-step guidance.

## Who Would Use It

- Firmware engineer checking Host, FTL, or NAND behavior
- Validation engineer investigating a test failure
- RMA/support engineer triaging customer symptoms
- AI engineer building internal tools for storage engineering teams
- Software engineer building engineering knowledge systems

## Industrial Features

### 1. Evidence-Based Question Answering

The assistant retrieves relevant notes before answering. Each answer returns citations with:

- note title
- source file
- subsystem/topic
- retrieval score

Why it helps industry:

- engineers can verify where an answer came from
- the assistant does not behave like a blind chatbot
- answers are easier to trust during debugging

### 2. Subsystem Classification

The app classifies the issue into:

- `Host`
- `FTL`
- `NAND`
- `Hardware`
- `Unknown`

Why it helps industry:

- triage can be routed to the right owner faster
- interviewers can see that the app understands storage-controller workflow boundaries
- it maps well to Maistorage's Host, FTL, and NAND firmware layers

### 3. Evidence Quality and Confidence

The app labels retrieved context as:

- `strong`
- `moderate`
- `weak`
- `insufficient`

It also returns a confidence score.

Why it helps industry:

- weak evidence is flagged instead of being hidden
- users know when more logs or documents are needed
- this reduces hallucination risk

### 4. "Not Enough Evidence" Behavior

When no useful note is retrieved, the assistant tells the user that evidence is insufficient and requests more context.

Why it helps industry:

- avoids false root-cause claims
- supports safer engineering decisions
- matches how real technical support tools should behave

### 5. Document Intake

Users can upload:

- `.txt`
- `.md`
- `.log`
- `.csv`
- `.json`

The app chunks the uploaded content and indexes it into the current session.

Why it helps industry:

- engineers can add validation logs or new troubleshooting notes
- support teams can test the assistant with fresh issue reports
- the system behaves closer to an internal knowledge assistant

### 6. Recommended Debugging Actions

Each subsystem produces practical next actions.

Examples:

- NAND: review ECC trend, read-retry counters, bad-block growth
- FTL: review mapping-table changes and garbage-collection pressure
- Host: inspect command queue and timeout sequence
- Hardware: correlate resets with temperature and voltage events

Why it helps industry:

- the output becomes action-oriented
- junior engineers get structured guidance
- interviewers can see real troubleshooting thinking

## Tech Stack

- Python
- FastAPI
- Pydantic
- HTML/CSS frontend
- local keyword retrieval
- optional OpenAI Responses API
- upload handling with `python-multipart`

## Default Model

Default:

```text
gpt-5.4
```

Why:

- firmware Q&A benefits from stronger reasoning
- answers must stay grounded in retrieved evidence
- this is the most reasoning-heavy project among the three

For faster or cheaper testing:

```bash
OPENAI_MODEL=gpt-5.4-mini
```

The app still works without an API key using deterministic fallback answers.

## Project Structure

```text
app/
  main.py                 FastAPI app, retrieval, classification, upload indexing
  templates/index.html    engineering evidence console UI
  static/styles.css       operational dashboard styling
data/
  knowledge_base.json     starter firmware/NAND notes
  uploads/                uploaded engineering notes
requirements.txt          dependencies
README.md                 project guide
```

## API Endpoints

- `GET /` opens the web UI
- `GET /api/knowledge` lists loaded knowledge notes
- `POST /api/ask` answers a question with citations, subsystem, confidence, and actions
- `POST /api/upload` indexes a text/log/CSV/JSON engineering note
- `GET /health` checks service status

## How To Run

```bash
cd "G:\Ai Project\ssd-nand-firmware-knowledge-assistant"
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Open:

```text
http://127.0.0.1:8001
```

Optional:

```bash
set OPENAI_API_KEY=your_key
set OPENAI_MODEL=gpt-5.4
```

## Demo Questions

- `Why would read retry count spike after a firmware update?`
- `What can cause write latency during garbage collection?`
- `What should I inspect when controller resets increase with temperature?`
- `How should I inspect a power loss recovery issue?`

## Interview Explanation

Say this:

> This project is a firmware knowledge assistant for SSD/NAND teams. It retrieves relevant engineering notes, classifies the issue into Host, FTL, NAND, or Hardware, reports evidence confidence, returns citations, and recommends practical debugging actions. I designed it to reduce manual document search and make AI answers safer for engineering workflows.

## Resume Bullet

Built an SSD/NAND firmware knowledge assistant using Python, FastAPI, retrieval logic, document upload, subsystem classification, evidence scoring, and LLM-based answer generation to support citation-backed firmware troubleshooting.

## Production Hardening Ideas

- replace keyword retrieval with vector search
- persist uploaded documents in a database
- add access control for confidential engineering documents
- add PDF parsing
- add audit logs for every answer
- add evaluation tests for answer grounding
- add Docker and deployment pipeline
