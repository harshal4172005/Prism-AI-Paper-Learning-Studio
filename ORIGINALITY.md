# Contribution, attribution and current evidence

Prism extends this repository's earlier multimodal RAG prototype into a private paper-learning studio. The implemented workflow connects document-grounded explanations, original PDF pages, conversational follow-ups, source switching, multi-paper comparison, a notebook, quizzes and numerical lessons. Accounts and durable conversations support returning users. Storage is bounded through deduplication, lazy previews, cache eviction and usage limits.

This application code was implemented for this repository. That does not establish unprecedented concepts, the provenance of the pre-existing code, or a new scientific discovery. No new foundation model, attention algorithm or training method was developed. The numerical lessons illustrate known methods; they do not reproduce the original paper's trained-model results.

Prior work relevant to evidence and citation evaluation includes [ALCE](https://arxiv.org/abs/2305.14627) and [RAGChecker](https://arxiv.org/abs/2408.08067). Their code was not copied to implement this extension. The attention lessons are based on established Transformer concepts.

A defensible portfolio description is: "I built a private PDF learning assistant that combines source-grounded conversations, multi-paper comparisons, original diagrams, a notebook and interactive numerical lessons in a resource-bounded deployment."

Validation: 29 automated Python checks pass, together with numerical checks across all five lessons. Hosted tests verified signup, PDF upload, adaptive follow-ups, a real two-paper comparison, a generated three-question quiz and feedback, notebook persistence, original-page reading and chat restoration after reload. A second account was denied access to the first account's documents, images and conversation. Existing website config hashes were unchanged and existing HTTPS sites remained healthy.

These are functional checks, not a professional security audit, proof of factual accuracy, demonstrated educational effectiveness or research novelty. To establish impact, use a held-out question set and a reader study comparing comprehension, unsupported-claim detection, task time and API cost against a plain PDF reader or ordinary RAG chat. Report uncertainty and negative outcomes as well as improvements.

Current limits include lexical retrieval, bounded recent conversation context, no OCR or email recovery delivery, no external automated backup, and no independent semantic-entailment evaluator. Important conclusions still require inspection of the original sources.
