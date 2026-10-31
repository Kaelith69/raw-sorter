---
name: premium-readme
description: "Create or refresh a premium, technically accurate GitHub README with original local SVG/SMIL motion graphics. Use when documenting a repository, designing an animated project page, building architecture/workflow diagrams, or validating README asset links."
argument-hint: "[repository path or project name]"
user-invocable: true
---

# Premium README

Use this workflow to turn an existing repository into a polished documentation page without inventing capabilities.

## Procedure

1. Inspect the complete repository: source files, dependency manifests, configuration, tests, entry points and existing docs.
2. Extract only verified behavior: supported commands, platforms, file formats, module boundaries, environment variables, installation flow, current project status and the repository's actual license state.
3. Create a visual system before writing prose: dark graphite base, one cool accent, one warm accent, consistent `viewBox`, explicit dimensions and readable text at mobile widths.
4. Add project-specific assets under `assets/`:
   - `hero.svg` for identity and a restrained animated header.
   - `architecture.svg` for components and data flow.
   - `workflow.svg` for sequential execution.
   - `feature-icons/` for meaningful feature illustrations.
   - `animations/` for demonstrations.
   - `diagrams/` for technical detail.
   - `fallbacks/` for a static equivalent where motion is not desirable.
5. Use GitHub-compatible SVG only: XML namespaces, SMIL (`animate`, `animateTransform` or `set`), no JavaScript, no external CSS and no remote runtime dependencies.
6. Write README sections for overview, features, architecture, stack, structure, installation, usage, workflow, testing, status, contributing and license. If no license exists, do not imply open-source permissions; ask for the intended license before creating one.
7. Validate every SVG as XML, check that every README asset reference exists, and run the repository’s smallest relevant syntax/build/test command.
8. Inspect rendered previews when a browser or SVG renderer is available. Look for clipped text, overlapping labels, overflow, unreadable contrast and broken animation timing. If a renderer is unavailable, perform XML and dimension validation and provide a static fallback.

## Quality rules

- Never claim a feature, percentage, API endpoint, platform or license that the repository does not support.
- Prefer diagrams that explain a relationship over decorative motion.
- Keep animation subtle and finite where possible; use `repeatCount="indefinite"` only for ambient indicators.
- Include meaningful `alt` text or SVG `title`/`desc` content.
- Preserve existing behavior and use the repository’s naming and commands.
