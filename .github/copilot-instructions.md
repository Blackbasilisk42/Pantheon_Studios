# Pantheon Studios Copilot Instructions

All future code modifications must be applied directly within workspace files.
Do not provide standalone replacement code blocks in chat when the request is to implement or edit code.
Use direct file edits so the repository remains the source of truth.

Human-in-the-Loop policy is mandatory:
- New generated content should enter queue/pending/ first unless explicitly marked otherwise by a human decision.
- Only content approved by a human should remain in queue/approved/ or be published onward.
- Rejected content should be moved to queue/rejected/ with rejection context retained when possible.

Platform extension rule:
- All future publishing or distribution platform extensions must be implemented under publishers/.
- Shared publishing abstractions should extend publishers/base_publisher.py.
