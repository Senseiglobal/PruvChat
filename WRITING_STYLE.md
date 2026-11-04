# PruvChat Writing Style Guide

One central guide for every word the user reads: body copy, helper text,
tooltips, alerts, empty states, instructions, and generated explanations.

## Rules

1. Never use em dashes. Use a full stop and start a new sentence instead.
2. Avoid hyphens and dash punctuation in body copy. Prefer commas, full
   stops, or separate short sentences.
3. Write naturally, warmly, and clearly, as if explaining to a friend.
4. Keep sentences short and concise. One idea per sentence.
5. Use everyday words that a child could understand.
6. Explain technical terms on first use, briefly, in plain words.
7. Avoid jargon, robotic phrases, repetition, and unnecessary detail.
8. Give direct, helpful instructions. Say what to do next.
9. Keep safety and uncertainty warnings accurate. Never soften a warning
   to sound friendly, and never overstate what was checked.
10. Never alter URLs, file paths, code, API fields, identifiers, verdict
    labels, citations, evidence quotes, or technical data to fit these
    rules. Protected values stay byte for byte.

## Exemptions

These keep their exact form: `MODEL_API_KEY`, `.env` paths, model IDs,
claim and evidence IDs (`r1`, `e1`, `w1`), verdict labels, `UNVERIFIED`,
`MOCK MODE`, `LIVE MODE`, method strings starting with `live`, error
codes, established API error phrases, and compact count labels such as
`claim(s)` and `N file(s)`.

## Applying the rules to generated text

Template rationales, fallback reasons, and mock explanations follow this
guide. Live model rationales come from the API and cannot be rewritten;
they are shown as returned, with their citations checked, never invented.

## Checking

`python -m pytest tests/test_style.py -q` fails if em dashes, en dashes,
or ASCII double hyphens appear anywhere in product code. Prose hyphens
are caught by review against this guide, since code identifiers
legitimately contain hyphens.
