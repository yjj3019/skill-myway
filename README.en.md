# skill-myway

> **한글**: [README.md](./README.md)

A personal collection of skills for Korean writing, office documents, security analysis, development logging, incident RCA, code review, prompt design, research briefs, and evidence-first reviews. The skill content lives in one set, and Claude Code, ChatGPT (Codex), and Grok Build all read the same `SKILL.md`. In Grok Bot the skill is stored from a conversation instead of installed as files.

## Skills

| Skill | What it does |
| --- | --- |
| `writing` | Writing and editing Korean blogs, technical posts, articles, and work documents. Includes personal-information checks and per-runtime adjustments |
| `office-docs` | PPTX/DOCX/XLSX authoring specs, long DOCX builds, reading HWP/HWPX sources |
| `rhel-cve` | RHEL CVE impact analysis and Confluence-ready reports based on Red Hat sources |
| `devlog` | Logs development history to Notion. Falls back to `SESSION_LOG.md` when not connected |
| `incident-rca` | Incident and error RCA: separates timeline, hypotheses, and evidence, then regression-prevention actions |
| `code-review` | Code change review: severity, evidence, Validation Gap, weakening tests |
| `prompt-engineering` | Prompt structuring, review, and evaluation-case design |
| `research-brief` | Research briefs that state source grades and reference dates |
| `evidence-first` | Evidence-first review: completion evidence, stale/conflicting guidance, independent verification |

## Installation

### Claude Code

```text
/plugin marketplace add yjj3019/skill-myway
/plugin install myway@skill-myway
```

On the command line, marketplace paths must start with `./`, e.g. `claude plugin marketplace add ./`. Update with `/plugin marketplace update skill-myway`.

### Codex

```sh
codex plugin marketplace add yjj3019/skill-myway
codex plugin add myway@skill-myway
```

Update with `codex plugin marketplace upgrade skill-myway`, remove with `codex plugin remove myway@skill-myway`. Restart the app after installing and confirm the version with `codex plugin list`.

### Grok Build

Grok Build reads the Claude Code marketplace, plugin, and skill format as-is. If you installed the plugin in Claude Code, no extra step is needed.

```sh
grok plugin marketplace add yjj3019/skill-myway
grok plugin install myway@skill-myway --trust
```

When a local folder is added as a marketplace, its folder name becomes the marketplace name. In that case omit the name, `grok plugin install myway --trust`, or use `myway@<folder-name>`. Update with `grok plugin update`.

To use the skills without the plugin, copy them to `~/.grok/skills` with the install script below.

### Grok Bot

Instead of installing files, store the skill from a conversation. Paste the `SKILL.md` content in one go and ask, for example:

> Save these instructions as the `writing` skill. Include inputs, verification steps, and the approval boundary.

If the team feature is available you can publish the skill to share it. Storage behavior varies by account and app UI, so confirm in the list.

### Claude App and ChatGPT Skills

Package an upload ZIP, then install it from the app's Skills menu.

```sh
python3 scripts/package_skill.py --skill writing
```

This produces `dist/myway-writing-<version>.zip`; the ZIP contains `<skill-name>/SKILL.md` and `references/`. Upload menus and limits vary by account and app version.

### Installing Skills Directly

```sh
python3 scripts/install_skills.py --target all          # Claude Code, Codex, and Grok Build
python3 scripts/install_skills.py --target claude       # ~/.claude/skills
python3 scripts/install_skills.py --target grok         # ~/.grok/skills
python3 scripts/install_skills.py --dest <path>         # any location
```

`--link` creates symbolic links instead of copies (Windows may require elevated privileges); `--force` replaces an existing skill with the same name. Installed skills are not auto-updated, so pull the repository and reinstall.

## Paths Read per Platform

| Platform | Marketplace | Plugin manifest | Skill path |
| --- | --- | --- | --- |
| Claude Code | `.claude-plugin/marketplace.json` | `plugins/myway/.claude-plugin/plugin.json` | `plugins/myway/skills/<name>/SKILL.md` |
| Codex | `.agents/plugins/marketplace.json` | `plugins/myway/plugin.json` (canonical), `.codex-plugin/plugin.json` (compat) | `plugins/myway/skills/` |
| Grok Build | `.grok-plugin/marketplace.json` (Claude format also works) | `plugins/myway/plugin.json` (optional) | `~/.grok/skills`, `~/.agents/skills`, plugin `skills/` |

Full requirements and unverified items are in [platform support status](docs/PLATFORMS.md).

## Brand Profile

`office-docs` looks for brand settings in this order: values given in the request, `brand-profile.md` in the working directory, `~/.claude/myway/brand-profile.md`, and neutral defaults. The profile template is [brand-profile.md](plugins/myway/skills/office-docs/references/brand-profile.md). Organization-specific values are never stored in the repository.

## Companion Skills

For proposals, RFPs, slide decks, and submission reviews, use [ProposalSkills](https://github.com/yjj3019/ProposalSkills) as a separate plugin. This repository covers everyday writing, documents, security, incident analysis, and code review; proposal-only content, PPTX builds, and the submission gate live in ProposalSkills. Files are never copied between the two repositories.

## Verification and Maintenance

```sh
python3 scripts/validate_repo.py                        # structure, versions, sensitive patterns
python3 scripts/run_tests.py                            # treats 0 tests or skipped tests as failure
python3 scripts/package_skill.py --skill all            # upload ZIPs
```

The validator checks manifests, version consistency, skill guidance and reference files, script syntax, and sensitive patterns. Terms that cannot live in the repository are passed with `--terms <file>` or the `MYWAY_BANNED_TERMS_FILE` environment variable and are never committed.

Quality criteria are in [quality bar](docs/QUALITY-BAR.md) and the skill authoring process in [skill authoring guide](docs/SKILL-AUTHORING.md). Review severity and evidence criteria are in [review contract](docs/REVIEW-CONTRACT.md), and quality comparisons for skill changes in [skill evaluation](docs/EVALUATION.md). Run blind comparison packets with `python3 scripts/blind_review.py --help`; simulated and real evaluations with `python3 scripts/simulate_eval.py` and `python3 scripts/run_eval.py --help`. Real evaluation results are in [evaluation results](docs/EVALUATION-RESULTS-2026-11-01.md).

When changing a skill, bump `VERSION` and the version in every platform manifest. Verified and unverified items are recorded in [verification status](docs/VERIFICATION.md).

## License and Sources

This repository is licensed under the [Apache License 2.0](LICENSE). License and source assessments from the integration work, including what was absorbed and what was excluded, are in [license and source review](docs/LICENSES.md). Nothing is copied from external repositories verbatim; everything is newly written, and no real names, organizations, real post citations, or internal information are kept in the repository.

Criteria live in `docs/DECISIONS.md` and regression-prevention lessons in `docs/compound-log.md`.
