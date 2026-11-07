# Prism — private paper learning studio

Hosted at https://prism.140.245.195.222.sslip.io/

## Use it

1. Create an account. Save the recovery key shown once. Recovery uses that key; email delivery and email verification are not configured.
2. Open **Papers**, upload searchable PDFs, and select up to five for your next reply.
3. Ask questions and follow-ups in the same conversation. Use **Simpler please**, **Give an example**, **Show the maths**, **Explain the diagram**, or **Check my understanding**.
4. Switch papers whenever needed. Earlier replies retain their original source snapshots. Use **Compare selected papers** when two or more PDFs are selected.
5. Reopen, search, rename, export or delete conversations in **Chats**. Pending replies continue in the background. Failed/interrupted replies have retry controls.
6. Read original PDF pages beside the answer, with page navigation and an original-file link. Source controls open the matching location; original page images can be enlarged.
7. Save explanations or personal notes in **My notebook**. Edit notes and export the notebook or a conversation as Markdown. Account export is JSON.
8. Explore five numerical lessons: attention scaling, softmax, causal masking, positional encoding and toy attention heads. Download their real computed measurements.

The lessons illustrate known concepts, not trained-model performance or scientific discoveries.

## Accounts and privacy

Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Sessions are random, stored as hashes, revocable, and sent in HttpOnly cookies (Secure on the hosted site). Ownership checks protect every document, page image, chat and note. Key-based password recovery rotates the recovery key and revokes existing sessions. Account deletion requires the password.

PDFs are stored once by content hash; account ownership is separate from physical storage. Deleting a PDF removes its file only after no account references it. Historical explanations and excerpts remain in saved messages until their conversation/account is deleted.

When asking a question, retrieved text and up to four original page images are sent to configured AI providers. Previous answers provide conversational context, not independent evidence. Images are rendered original pages, not AI-created illustrations or precise crops. The model can still make mistakes.

## Hosted limits

- 12 MB per upload; 100 pages per PDF.
- 10 PDFs / 50 MB of originals per account; up to five selected per conversation.
- 100 conversations, 500 saved turns and 100 notebook entries per account.
- 25 AI questions per account per UTC day; 150 across the installation; two concurrent generations.
- Application data admission budget: 384 MB, with small cache/database housekeeping overhead.
- Lazy JPEG page previews; 32 MB cache cap. No eager page-image generation.
- Process cap: one CPU core and 512 MB memory; 384 MB memory high-water control.

Initial deployment measured about 52 MB idle process memory and 120 MB of installed application/dependencies. No GPU service, model downloads, Docker image or separate vector database is required.

## Local development

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-server.txt
.\venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Configure a Gemini API key in `.env`; optional Groq/NVIDIA text fallbacks are supported. The default generation model is `gemini-2.5-flash`. Hosted integration uses REST, avoiding the provider SDK. Uploaded documents use SQLite FTS5/BM25 retrieval. Legacy Qdrant/embedding CLI modules remain for reference but are not imported or exposed by the private web server.

For tests install `httpx`, then run:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/test_experiment.cjs
```

29 Python checks cover authentication, recovery, session revocation, cross-account denial, history persistence, follow-up context, multi-paper snapshots, duplicate requests, shared-file cleanup, quotas, exports and prior ingestion/audit behavior. Numerical checks cover all five lessons. These checks establish functional behavior, not educational or factual-accuracy improvement.

The tested ARM server dependency versions are recorded in `deploy/requirements-server.lock`. See `deploy/OPERATIONS.md` for isolated deployment details.

## Current limits

Scanned PDFs require OCR before upload. Retrieval is lexical and may miss paraphrases. The latest eight completed turns provide model context; complete history is still saved. Comparisons depend on relevant evidence from each selected paper. No semantic entailment certification, novelty or benchmark improvement is claimed.

The temporary hostname depends on third-party DNS. A domain you control is preferable for long-term hosting. Automated external backups and email recovery are not configured.

Security references: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). Provider integration follows the [Gemini API reference](https://ai.google.dev/api).

## CI/CD

GitHub Actions tests Python 3.11/3.12, numerical lessons, deployment safety and source hygiene. Successful main-branch changes deploy a checksummed artifact to the isolated Oracle service with commit-specific health checks and automatic code rollback on startup failure. See `deploy/CI-CD.md` for access boundaries, retention, database snapshot behavior and operating instructions.
