# UCB Affiliation

Tools for looking up a UC Berkeley user's affiliation with a department -
employment, academic programs, course enrollment, group membership, and
teaching/TA assignments - by querying HR, SIS, Grouper, and LDAP in
parallel via [flowtoy](https://github.com/flowtoy/flowtoy).

Two ways to use it, sharing the same core lookup and affiliation-determination
logic:

- **[CLI tool](cli.md)** (`affiliation-lookup`): scripting, bulk reporting,
  ad hoc lookups from the terminal.
- **[Web application](webapp.md)** (`ucb_affiliations.web`): CalNet OIDC
  self-service affiliation check, plus an admin `/lookup` tool with live
  per-source results.

See [Architecture](architecture.md) for how the pieces fit together and
which parts are shared.
