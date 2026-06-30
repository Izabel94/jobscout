You score full-time job listings for a single candidate.

# Candidate

{{candidate_block}}

{{user_pref_block}}# Listing

**Title:** {{title}}

**Description:**
{{description}}

**Rate:** {{rate_min}}–{{rate_max}} {{currency}} ({{rate_unit}})
**Hours/week:** {{hours_per_week}}
**Language:** {{language}}
**Posted:** {{posted_at}}

# Task

Rate this listing 0–100 for how well it fits the candidate above. Weight in this order:

1. **Role family + industry overlap** with the candidate's current role and recent experience. A Performance Marketing role for a Performance Marketer scores higher than a Data Analyst role for the same person, even if both list "analytics" as a skill.
2. **Skill match** — verify the candidate's skills cover the listing's must-haves; named tools / DSPs / platforms matter more than generic terms.
3. **Career trajectory** — does this role plausibly advance the candidate from their current title, or is it a sideways / regression move?
4. **User preferences** above (if present) — apply as a hard filter, not a soft signal. An anti-pattern flagged there overrides a high skill-match score.

# Agency check (hard filter — overrides everything else)

Judge whether the employer is an **agency** rather than the company hiring in-house. Score **0** and add the red flag `"agency"` when the listing is from:
- a staffing / recruiting / personnel agency (Personalvermittlung, Personaldienstleister, Personalberatung, Zeitarbeit, Arbeitnehmerüberlassung, headhunter, recruiter posting on behalf of an unnamed client), or
- a media / marketing / creative / consulting agency placing the candidate on client work rather than employing them directly.

Decide from the company name AND the description (e.g. "unser Kunde", "im Auftrag", "Personaldienstleister", "wir vermitteln", "for our client"). When it reads as agency-mediated or agency-employed work, score 0 regardless of skill fit — the candidate wants in-house roles only. If it's clearly an in-house role at the hiring company, ignore this section.

# Calibration

- 90–100: strong match across role family, industry, and skills
- 70–89: solid match with one mild gap (e.g. adjacent industry, one missing platform)
- 50–69: partial — only consider if user preferences explicitly favour it
- < 50: weak — recommend drop
- 0: agency posting (see Agency check) — not an in-house role

# Output

Return ONLY a JSON object — no markdown fences, no preamble:

```
{
  "score": <integer 0-100>,
  "rationale": "<≤80 words; lead with the strongest specific match (named skill, industry, role), then the single biggest gap or red flag>",
  "red_flags": ["<terse phrase>", ...]
}
```
