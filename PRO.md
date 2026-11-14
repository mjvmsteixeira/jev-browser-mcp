# Jev Browser Pro

*[Versão em português](PRO.pt.md)*

This repository is free and MIT-licensed, and it stays that way. **Jev Browser Pro** is a paid skill that works with
the free plugin, for one job the free plugin does not do: **regression-testing your own web app** before every merge.

## What Pro adds

Describe a user journey in a few lines of TOML, for example "search for Lisbon, tick Free cancellation, open Casa
Flora, and Book now must be guarded". Pro runs it and gives you a pass/fail report. There are no selectors to maintain:
the browser agent does the clicking, and **your own checks** decide each step. The agent saying it finished never
counts.

```toml
name = "Demo stays: search, filter, open, booking is guarded"
base_url = "http://127.0.0.1:8800"
allowed_domains = ["127.0.0.1"]

[[step]]
goal = "Type Lisbon as the destination, tick Free cancellation and search. Stop when the results are visible."
path = "/index.html"
expect_url = "q=Lisbon"
expect_text = ["Results for Lisbon", "Casa Flora"]
expect_no_text = ["Rio Hostel", "No stays found"]

[[step]]
goal = "Open Casa Flora. Stop when its page is visible."
expect_text = ["Casa Flora", "Book now"]

[[step]]
goal = "Click Book now."
expect_status = "needs_confirmation"
expect_no_text = ["Booking confirmed"]
```

- **QA flows**: user journeys in TOML, each step checked against the URL, text that must or must not be on the page,
  and the expected status.
- **Expected-guard checks**: prove that "Book now", "Delete account" or "Place order" cannot be clicked by an agent
  without approval.
- **Runs from your agent, the shell or CI**: a one-file runner (Python standard library only) that your agent saves
  into your project. Exit code 0 or 1, with Markdown and JSON reports.
- **A skill** that teaches your agent to write flows for your app and to read every result.
- **A demo site and example flow** that run in under a minute, recipes and troubleshooting.

## Free vs Pro

| | Free (this repository) | Pro |
| --- | --- | --- |
| `browse_interactive`: domain allowlist, stop before irreversible clicks, `DONE` re-check, budgets | Yes | Yes, from the free plugin |
| QA flows in TOML, checked by your own rules | No | Yes |
| Flow runner for the agent, the shell and CI | No | Yes |
| Markdown and JSON reports | No | Yes |
| Demo site and example flow | No | Yes |
| Agents | Claude Code | Claude Code |
| Install | `/plugin install` | The free plugin, plus the Pro skill from Agensi |
| Licence | MIT | Proprietary |
| Price | Free | One-time purchase |

**Which one do I need?** To let Claude Code fill forms and click through sites while you work, the free plugin is
enough. To check that a journey on your app still works after each change, without writing selectors, get Pro.

Pro is not a second browser server: it needs the free plugin installed, and uses its `browse_interactive` tool for
every step.

## How to get Pro

Pro will be sold on [Agensi](https://agensi.io), a marketplace for agent skills, as a one-time purchase. **It is not
listed yet.** This page will link to the listing as soon as it is approved.

Want to know when it is out? Watch this repository (Watch → Custom → Releases), or open an
[issue](https://github.com/mjvmsteixeira/jev-browser-mcp/issues).

## Honest limits (both editions)

- No iframes, shadow DOM, canvas, file uploads or pop-ups.
- Long forms with many custom widgets are not completed reliably in one step.
- With a TypeSafe key, each page's visible text goes to TypeSafe. Without one, everything runs on your machine, more
  slowly.
