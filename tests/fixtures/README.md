# Test fixtures

These fixtures are used by the source-adapter tests. Each subdirectory corresponds to a source.

## upwork/
- `sample.xml` — captured Upwork RSS feed.

## bundesagentur/
- `sample.json` — **stub fixture**. Plausible payload modeled on the Bundesagentur Jobboerse API
  (`https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs`, header `X-API-Key: jobboerse-jobsuche`).
  Replace with a real captured payload when the API is accessible.

## freelancermap/
- `sample.html` — **stub fixture**. Plausible HTML snapshot of a freelancermap project listing page.
  Replace with a real captured page when accessible.
