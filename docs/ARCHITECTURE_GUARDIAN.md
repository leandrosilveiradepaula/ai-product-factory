# Architecture Guardian

## Purpose

The Architecture Guardian is the deterministic primary scanner used by the Security specialist lane. It inspects the exact pull-request candidate and produces structured findings plus factual impact surfaces.

## Blocking invariants

Version 1 blocks concrete patterns such as:

- literal OpenAI, Supabase or GitHub secret-like tokens;
- private-key material;
- client-exposed service-role/secret/private-key environment names;
- pull_request_target additions;
- write-all workflow permissions;
- danger-full-access;
- SECURITY DEFINER additions;
- disabling row-level security;
- permissive grants to public, anon or authenticated;
- public RLS policies aimed at public/anon/authenticated.

Only critical/error findings fail the Security lane.

## Evidence-required warnings

Some changes are risky surfaces but are not vulnerabilities by themselves:

- dependency manifest or lockfile changes;
- API route/surface changes;
- destructive schema operations.

These produce warnings and explicit evidence requirements rather than invented failures.

## Factual maps

The Guardian extracts:

- sensitive paths;
- changed workflow files;
- dependency surfaces;
- API contract surfaces;
- SQL objects created/altered/dropped;
- SQL table/function references useful for migration lineage.

This is evidence for Impact/DoD/Release Intelligence. It is not represented as a complete semantic dependency graph when the diff cannot prove one.

## Explicit unknown coverage

Version 1 explicitly reports false for checks it did not execute:

- dependency vulnerability scan;
- SBOM generation;
- full SAST;
- semantic API compatibility.

Unknown coverage must remain unknown until a real deterministic scanner supplies evidence. The Factory must never translate missing evidence into pass.

## Model boundary

The scanner makes no model call. A future Security model may interpret or prioritize deterministic findings, but it does not replace the scanner as source of truth.

## Repair integration

Blocking Security findings include file/scope provenance. When safely repairable, the bounded repair controller can assign a Development work unit restricted to those scopes. The repaired candidate then repeats CI and all required specialist lanes.