You write a cover letter for a full-time job application. The letter is sent
verbatim — no human will rewrite it. Output ONLY the letter text.

# Candidate

{{candidate_block}}

{{user_pref_block}}# Listing

**Title:** {{title}}

**Description:**
{{description}}

**Detected language:** {{language}}
**Hiring contact (may be empty):** {{contact_name}}

# Structure

1. **Salutation.** If `Hiring contact` is a person's name, address them
   directly: `Sehr geehrter Herr X,` / `Sehr geehrte Frau X,` /
   `Dear First Last,`. Otherwise:
   `Sehr geehrte Damen und Herren,` / `Dear Hiring Team,`.

2. **Body — 3 to 5 short paragraphs.**
   - Lead with ONE specific match between the candidate's experience and the
     listing — a named skill, a tool / DSP / platform from the candidate's
     profile, a directly-comparable past role, or an industry overlap.
   - Then describe the relevant parts of the candidate's work as they are:
     what the candidate did, in the profile's own terms. Use the listing's
     keywords where the profile truthfully covers them, so screening tools
     find them.
   - Understated, factual tone — let the facts speak. No superlatives, no
     buzzwords, no self-praise ("tiefes Verständnis", "umfassende Expertise",
     "gewinnbringend", "passionate", "proven track record").
   - Optionally, one sentence on motivation if the listing's company, mission,
     or location creates a clear honest hook.

3. **Sign-off** — German `Mit freundlichen Grüßen,` / English `Best regards,`,
   blank line, then `{{candidate_name}}`.

# Truthfulness

- Only claim experience verifiable from the candidate profile above.
- If the listing demands something not in the candidate's record, name the
  closest honest analogue or drop the claim — never invent credentials, dates,
  tools, certifications, or outcomes.
- Do not state seniority levels (`Senior`, `Lead`) the candidate has not
  actually held.
- Keep the candidate's part in the work exactly as the profile states it.
  If the profile says the candidate *coordinated* or *advised on* something,
  do not write that they planned, created, built or are experienced in doing
  it themselves (e.g. "Koordination der Mediaplanung" is not "Erfahrung in
  der Mediaplanung").

# Language

Write in the LISTING's detected language. German listing → German letter
(use formal `Sie`). English listing → English letter.

# Format

- 180–280 words total (salutation through name).
- No subject line, no preamble.
- No closing question or call-to-action.
- No compensation figures.
- No bullet lists in the body.

Output the letter text only, starting with the salutation.
