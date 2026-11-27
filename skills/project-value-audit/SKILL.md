---
name: project-value-audit
description: Rigorously audit a local software project (or force-rank a portfolio of side projects) across Marginal Learning, Personal Utility, Open-Source Signal, Commercial Viability, and Maintenance/Opportunity Cost. Use when the user asks whether a project is worth continuing, worth spending more tokens on, worth open-sourcing, worth commercializing, already solved by existing tools, or ready to archive/kill.
---

# Project Value Audit — Evidence-First, Anti-Sycophancy Evaluation

Evaluate local projects honestly so the user stops leaking tokens, attention, and weekends into low-ROI repos.

## Core Anti-Sycophancy Rules (Mandatory)

1. **Never output a single mushy overall score.** Always separate the 4 independent value axes + 1 explicit cost axis.
2. **Separate sunk value from future marginal ROI.** Past effort, lines of code, or commit count are NEVER valid arguments for continuing.
3. **Run a mandatory Red-Team ("Kill Signals") pass first.** Before recommending any further investment, state at least 2 concrete, uncomfortable reasons to STOP, shrink, or archive the project.
4. **Evidence over README claims.** Inspect actual code structure, git cadence, tests, dependencies, and real usage signals — never take marketing copy in `README.md` at face value.
5. **Force a single verdict bucket.** No fence-sitting ("it depends, maybe keep going"). Pick ONE primary verdict and ONE time-boxed next step.

## Step 1: Collect Hard Internal Evidence (Local, Read-Only)

Before judging, inspect the target repository (and sibling repos if auditing a portfolio or if `mappo` is available):

- **Behavioral / Usage cadence**:
  - Total commits, active date span (first → last commit), burst vs. sustained cadence, dormant days since last commit.
  - Whether the project is actually deployed, installed, or dogfooded by the author.
  - Overlap with other local repos (e.g., multiple prototypes solving the same problem).
- **Engineering substance vs. wrapper ratio**:
  - Core modules, real domain logic / edge-case handling vs. thin CRUD / template / API wrapper.
  - Presence of tests, docs, CI, packaging, and whether it is 85% shippable or 15% skeleton.
- **Maintenance liability**:
  - Fragile dependencies: private schemas, scrapers, unstable external APIs, auth/billing/hosting ops, multi-platform burden.

*(If auditing multiple projects via `mappo`, run `mappo projects --indexed --json` and `mappo hygiene --indexed --json` to gather cross-agent activity, duplicate clones, and reclaimable disk space.)*

## Step 2: Collect External Market Evidence (If Search Is Available)

If web search tools are available in the current runtime:
- Search GitHub, Product Hunt, and developer communities using **generalized problem descriptions** (do NOT paste private repo names, internal identifiers, or raw source code into search queries).
- Classify the landscape honestly:
  - **Red Ocean / Commodity**: Mature incumbents with high adoption already solve 90% of this.
  - **Fragmented Intersection**: Adjacent tools exist, but a clear workflow gap remains.
  - **Localized / Ecosystem Blind Spot**: Existing tools ignore a specific OS, language, or local ecosystem.
- Assess **Platform Absorption Risk**: Will an upstream platform (Apple, Cursor, Anthropic, OpenAI, Notion, etc.) likely absorb this feature within 6–12 months?

If running offline (no web search), explicitly note that external market verification was skipped and base the verdict on internal engineering/usage evidence.

## Step 3: Score the 5 Decoupled Axes

Rate each axis `High` / `Medium` / `Low` (or `1–5`) with **concrete evidence** — never generic praise:

1. **Marginal Learning ROI (边际学习价值)**: What transferable skill or architecture is *still left* to learn if I keep building (distinct from what was already learned)?
2. **Personal Utility (个人实用价值)**: Real frequency (`daily / weekly / monthly / once`) × pain removed × switching cost vs. existing tools.
3. **Open-Source / Technical Calling Card (开源与技术名片价值)**: Would a senior engineer recognize genuine craft/differentiation within 15 seconds, and can they run it in < 60 seconds?
4. **Commercial / Indie Viability (商业与变现价值)**: Concrete willingness-to-pay, realistic distribution channel, retention frequency, and support/ops cost.
5. **Maintenance & Opportunity Cost (维护税与机会成本)**: Ongoing upkeep burden + what higher-compounding main quest this steals time/tokens from.

## Step 4: Deliver the Structured Audit Report

Output the report in this exact compact structure:

1. **Project Snapshot (Facts Only)**: What it actually does, tech stack, commit span & dormancy, completion level, local overlap.
2. **External Landscape (Real Substitutes)**: 3–5 concrete existing open-source / commercial alternatives and how this project compares honestly.
3. **5-Axis Assessment Table**: Marginal Learning / Personal Utility / Open-Source / Commercial / Maintenance Cost, each backed by 1–2 hard facts.
4. **Red-Team Kill Signals (At Least 2 Brutal Reasons to Stop/Shrink)**: Unfiltered risks and disqualifiers.
5. **Final Verdict (Exactly ONE Bucket)** + **Time-Boxed Next Action**:
   - **Double Down (主力投入)**: Clear moat + high compounding ROI.
   - **Ship & Park (收口发布，转被动维护)**: Strong calling card, low commercial ceiling; spend ≤ 1 day shipping cleanly, then stop active feature work.
   - **Keep Personal & Lean (保留自用，克制维护)**: Real personal utility, low external pull; maintain only when needed.
   - **Harvest & Archive (萃取资产后归档)**: Extract reusable patterns/components/prompts into personal harness, then slim/archive.
   - **Kill Cleanly (果断止损)**: Solved better elsewhere and no remaining learning/use value.

## Portfolio Mode (Force-Ranking Multiple Projects)

When auditing 3+ projects at once, **impose a scarcity cap**:
- Ask or assume a realistic weekly budget (e.g., 10 hrs/week).
- Allow **at most 1–2 projects** in `Double Down`; force all remaining projects into `Ship & Park`, `Keep Lean`, `Harvest & Archive`, or `Kill`.
- If `mappo` is installed and the user agrees, offer to persist decisions as tags (`mappo tag <id> flagship|ship|keep|archive`).
