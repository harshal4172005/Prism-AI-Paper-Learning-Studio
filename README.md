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

29 core Python checks cover authentication, recovery, session revocation, cross-account denial, history persistence, follow-up context, multi-paper snapshots, duplicate requests, shared-file cleanup, quotas, exports and prior ingestion/audit behavior. Numerical checks cover all five lessons. These checks establish functional behavior, not educational or factual-accuracy improvement.

The tested ARM server dependency versions are recorded in `deploy/requirements-server.lock`. See `deploy/OPERATIONS.md` for isolated deployment details.

## Current limits

Scanned PDFs require OCR before upload. Retrieval is lexical and may miss paraphrases. The latest eight completed turns provide model context; complete history is still saved. Comparisons depend on relevant evidence from each selected paper. No semantic entailment certification, novelty or benchmark improvement is claimed.

The temporary hostname depends on third-party DNS. A domain you control is preferable for long-term hosting. Automated external backups and email recovery are not configured.

Security references: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). Provider integration follows the [Gemini API reference](https://ai.google.dev/api).

## CI/CD

GitHub Actions runs 38 Python checks (29 application checks plus nine release/deployment checks) on Python 3.11 and 3.12, numerical lessons, syntax checks and source hygiene. Successful main-branch changes deploy a checksummed artifact to the isolated Oracle service with commit-specific health checks and automatic code rollback on startup failure. See `deploy/CI-CD.md` for access boundaries, retention, database snapshot behavior and operating instructions.


### Optional sample and usage

Readers can choose **Use sample paper** to add *Attention Is All You Need* to their private library. It never loads automatically or sends an AI question. The operator supplies the original PDF outside Git and release archives via `PRISM_SAMPLE_PDF` (defaults to `data/samples/attention-is-all-you-need.pdf`). Normal document quotas, deduplication and ownership checks apply.

The sidebar **Usage** panel shows daily request allowance with the local reset time, PDF storage, paper count, and account/per-chat **Vibe Points**. One point is one provider-reported token, including reported thinking. Tracking starts at this release; requests without usage metadata and older replies are not backfilled. A compact SQLite ledger retains usage after deleting a chat and is erased on account deletion. It also records a returned provider response when answer formatting fails.

Cost is a standard paid-tier equivalent, not a bill or user charge. Gemini 2.5 Flash standard text/image rates verified against https://ai.google.dev/gemini-api/docs/pricing on 2026-11-07: $0.30/M uncached input, $0.03/M cached input, $2.50/M output including thinking. Unknown models stay unpriced. This price mapping expires December 1, 2026 because Google advertises automatic model routing from that date; update the mapping when changing models. Browser lessons make no AI calls.


### Security and private provider usage

The production fallback order is Gemini, Groq (`GROQ_MODEL`, default `openai/gpt-oss-20b`), then NVIDIA (`NVIDIA_MODEL`, default `nvidia/nemotron-3.5-lightning-30b-a3b`). Set API keys only in the root-only server environment file; never in frontend code, Git, prompts, or URLs. The Usage panel reports each provider's measured calls, input/output Vibe Points and selected chat usage. Backup usage stays zero until that backup is called. Unknown pricing is shown as unavailable, not as a zero charge.

All chat, PDF, image, note, export and per-chat usage routes check the authenticated owner. Shared PDF bytes are deduplicated, but every account must separately add the PDF before it can access it. Client HTML and AI answers are rendered as text, and AI providers have no tools for filesystem, URL fetching, code execution or cross-account searches. Model instructions have a separate system role; retrieved text and history are explicitly untrusted data. This limits impact but does not guarantee perfect resistance to prompt injection.

Hardening includes secure HttpOnly SameSite session cookies in production, hashed passwords and session tokens, cross-origin/fetch-metadata checks, bounded JSON/upload bodies, redacted validation errors, private cache headers and a content security policy. Runtime dependency advisories and credential patterns are checked in CI. Production Pillow was upgraded to 13.0.0 after advisory review. The service runs with a dedicated user, no Linux capabilities, read-only application files, restrictive file creation permissions and a 512 MB memory limit.

Keys deliberately pasted into a chat remain in that chat's history; hiding server keys cannot erase that disclosure. Rotate them in the provider dashboards and update the private server environment. Do not expose the development server or reuse the production credentials for local tests. This is a targeted application review, not an independent penetration-test certification.


### Mobile chat and photo PDFs

On phones and tablets up to 900 px wide, Prism opens as a chat workspace: a top navigation bar, a slide-out drawer for history/papers/usage, independently scrolling messages, and a bottom composer. Learning demos open separately from the drawer. The supplied diamond logo is also used for the tab icon.

Photo/scanned PDFs use bounded local English OCR when no text layer is available. OCR-derived passages and answers are labelled, with original page images available to verify names, dates and numbers. Clear, upright printed pages work best; handwriting, blur and unsupported languages may fail. Install the native runtime described in `deploy/OPERATIONS.md` for a new server. Failed files are removed and stop using PDF quota; the library displays a private, dismissible error notice.
