# Project requirements and working rules

The official UCT INF4001N 2027 Geopolitics assignment PDF and official 2027
marksheet are primary authoritative requirements. The solo development plan is
supporting guidance. On this workstation the official PDFs are in the user's
Downloads directory, named `INF4001N - Entrance Exam - Geopolitics.pdf` and
`INF4001N MarksheetEntranceExam2027.pdf`. Ask for access if unavailable; never
invent an exam rule or silently substitute another year's brief.

Before implementing/modifying gameplay, read relevant sections of BOTH official
documents; identify mandatory rules and rubric criteria; distinguish them from
approved conventions in backend/docs/phase1-rules.md, phase2-rules.md and
phase3-npc-rules.md. Ask
about unresolved ambiguity. Do not omit mandatory requirements for convenience.
Maintain backend/docs/REQUIREMENTS.md with implementation/test/demo evidence and
report unmet mandatory requirements and rubric gaps in implementation reports.

Preserve existing functionality and regression tests. Keep engine logic independent
of FastAPI/MongoDB. Invalid actions must not mutate input/stored state. No public
gameplay write routes before explicitly approved access control. Human actor IDs
are not authenticated accounts. Phase 3 adds shared explainable NPC strategy;
authentication, frontend, visible fast-forward and AI commentary remain mandatory
future project work. NPC tie-breaking must never control battle dice. Preserve
human fingerprints and historical receipts when extending decision evidence.

Never display/log/commit passwords or connection strings. Do not change credentials,
environment variables or deployment configuration, or commit/push/deploy, without
explicit approval. No live Atlas data writes without explicit approval. Real
gameplay persistence tests must use an explicitly authorized disposable test
database, never production games. Mock tests do not prove transactions. No silent
fallback to non-atomic multi-document writes. Transactional gameplay writes default
to disabled until the documented real verification procedure passes.

Run isolated tests from backend with .venv/Scripts/python.exe, -c pytest.ini,
explicit tests/ selection, a unique Windows-compatible temporary --basetemp,
and -p no:cacheprovider. Never run/import backend/test_database.py during isolated
tests: it writes to Atlas at import. The opt-in real MongoDB suite is documented
in backend/docs/phase2-verification.md; do not run it without explicit approval.
