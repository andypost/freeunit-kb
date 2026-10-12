# zen-review PR #279 — isolation: reject "rootfs" + credential ns without a mount ns

_2026-09-08. Review of freeunitorg/freeunit#279. Forced update `1e43adac → 71b64952`
_+368/−1, 3 files. APPROVE. Config-time refusal of a kernel invariant._

## The bug
`rootfs` + `namespaces.credential: true` without `namespaces.mount: true` was
accepted, but the prototype died at every start; control API said only
`Failed to apply new configuration.` (or nothing, when started lazily).

## Root cause (kernel invariant — not fixable at runtime)
The child unshares `CLONE_NEWUSER` without `CLONE_NEWNS`
(`nxt_isolation.c:438-466`, `unshare` in `nxt_process.c:526`), so it holds
capabilities in a new user namespace while staying in the parent's mount
namespace, owned by the *initial* user namespace. `mount(2)` requires
`CAP_SYS_ADMIN` in the user namespace owning the mount ns → each automount in
`nxt_isolation_prepare_rootfs()` (`:926`) gets `EPERM` (`nxt_fs_mount.c:93`).
Nothing Unit can do at runtime; the only useful fix is to name the cause at
config time.

## The rule (deliberately narrow)
- The rootfs switch itself needs no mount ns — `nxt_isolation_change_root()`
  (`:1058`) falls back to `chroot(2)` (needs only `CAP_SYS_CHROOT` in the new
  user ns). So a config that mounts nothing starts and serves.
- The check fires only when a mount would be attempted: `tmpfs`/`procfs`
  (unconditional builtins, `deps=0`) or `language_deps` when the module declares
  mounts (`lang->mounts != NULL && nelts > 0`).
- Defaults agree: both validator and runtime default `language_deps/tmpfs/procfs=1`
  (`nxt_isolation.c:602-604`); validator passes `dflt=1` — identical.
- Generic: hook in `nxt_conf_vldt_app`, works for all langs via `lang->mounts`.

## Verdict: APPROVE (reinforced after forced update)
- ✅ Core config-time refusal correct; not over-strict (chroot path and
  no-automount stay valid).
- ✅ Error now NAMES the specific automount to switch off
  (`"or set \"automount\": {<name>: false}"`) — UX improvement.
- ✅ `declared-but-absent` line: the validator asks what the module DECLARES, not
  what runtime would mount (it also skips a bind whose `stat(src)` fails,
  `:930`). The author chose not to `stat()` host paths from the validator
  because it runs as the unitd user in the controller while the prototype
  mounts as root — same euid-signal problem in the other direction.
  `declared-but-absent` needs no FS access, doesn't change under the app's feet,
  and names the knob. Sound rejection of a Codex P2.
- ✅ New `test_python_isolation_rootfs_credential_language_deps`: at
  `procfs:false,tmpfs:false` the error names ONLY `"language_deps": false`
  (not the off procfs/tmpfs); the same config with `language_deps:false` is
  accepted. Both sides deterministic.

## Notes
- Refs the kernel `mount(2)`/user-ns invariant. P2 (Codex) rejected on
  euid-distinct grounds — correct.
- Sibling: zen-review-pr-265 (PHP automount mounts), pr-283/295 (no-body).
