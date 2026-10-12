---
title: "FreeUnit v2 PoC Overview"
description: "Proof of Concept: Rust orchestrator + NTS PHP workers on Revolt"
tags: [freeunit, v2, poc, rust, php, nts, revolt]
status: "PoC complete (2026-06-15)"
---

# FreeUnit v2 PoC Overview

**Philosophy:** FreeUnit v1 remains LTS, stable. FreeUnit v2 is an engineering exploration.

**This is NOT a Unit rewrite in Rust.** It is a new orchestrator.

## Key hypothesis

Hung detection via polling  (TGID invariant) works without FFI, without  in PHP, and without runtime changes.

## Live demo



-  — JSON with live worker PID
-  — hanging request

After 8 sec: master tears UDS, supervisor detects hang, PING_LIVENESS, SIGKILL, respawn.

## "Fair three-way" (freeunit2-a4v)

v2 vs RoadRunner vs FrankenPHP on the same hardware under s6-overlay.
One container, one CPU/kernel, postgres/valkey externally.

## Experiment: Rust + PHP-SAPI with Yii

A persistent PHP worker in Rust, embedding PHP through SAPI, without ZTS.
Standard NTS process managed by a Rust master. Goal: keep Yii3 app in memory between requests.

## PoC results

- 38/38 issues closed
- 76 tests green
- H1-H6 proven on PHP 8.5.7 NTS
- PoC development stopped
